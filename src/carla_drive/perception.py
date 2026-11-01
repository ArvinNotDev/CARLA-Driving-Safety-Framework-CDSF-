"""YOLOPv2 inference and its dedicated front-facing CARLA camera."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import carla

from carla_drive.camera.rig import LatestImage
from carla_drive.config import AppConfig

LOG = logging.getLogger("carla_drive.perception")

COCO_CLASSES = (
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
)


@dataclass(frozen=True)
class Detection:
    box: tuple[float, float, float, float]
    confidence: float
    class_id: int
    class_name: str


@dataclass(frozen=True)
class PerceptionFrame:
    detections: tuple[Detection, ...]
    driving_area: np.ndarray
    lane_lines: np.ndarray
    source_width: int
    source_height: int
    inference_ms: float
    received_at: float


class YoloPv2Model:
    """Run the provided YOLOPv2 ONNX graph and decode its three task outputs."""

    def __init__(self, model_path: Path, config):
        import cv2
        import onnxruntime as ort

        self._cv2 = cv2
        self._input_size = config.input_size
        self._confidence_threshold = config.confidence_threshold
        self._iou_threshold = config.iou_threshold

        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self._session = ort.InferenceSession(
            str(model_path),
            sess_options=options,
            providers=["CPUExecutionProvider"],
        )

        inputs = self._session.get_inputs()
        if len(inputs) != 1 or len(inputs[0].shape) != 4 or inputs[0].shape[1] != 3:
            raise ValueError("Expected a single YOLOPv2 image input with shape [1, 3, height, width].")
        self._input_name = inputs[0].name
        if isinstance(inputs[0].shape[2], int) and inputs[0].shape[2] != self._input_size:
            raise ValueError(f"Model input height is fixed at {inputs[0].shape[2]}, not {self._input_size}.")
        if isinstance(inputs[0].shape[3], int) and inputs[0].shape[3] != self._input_size:
            raise ValueError(f"Model input width is fixed at {inputs[0].shape[3]}, not {self._input_size}.")

        outputs = self._session.get_outputs()
        sequence_indices = [i for i, output in enumerate(outputs) if output.type.startswith("seq(")]
        anchor_indices = [
            i for i, output in enumerate(outputs)
            if len(output.shape) == 5 and output.shape[-1] == 2
        ]
        segmentation_indices = [
            i for i, output in enumerate(outputs)
            if len(output.shape) == 4 and output.shape[1] in (1, 2)
        ]
        driving_indices = [i for i in segmentation_indices if outputs[i].shape[1] == 2]
        lane_indices = [i for i in segmentation_indices if outputs[i].shape[1] == 1]
        if len(sequence_indices) != 1 or len(anchor_indices) != 3 or len(driving_indices) != 1 or len(lane_indices) != 1:
            names = ", ".join(output.name for output in outputs)
            raise ValueError(f"Unsupported YOLOPv2 output layout: {names}")
        self._detection_index = sequence_indices[0]
        self._anchor_indices = anchor_indices
        self._driving_index = driving_indices[0]
        self._lane_index = lane_indices[0]

    def infer(self, image: np.ndarray) -> PerceptionFrame:
        started = time.perf_counter()
        source_height, source_width = image.shape[:2]
        model_image, gain, pad = self._letterbox(image)
        tensor = model_image.transpose(2, 0, 1)[None].astype(np.float32) / 255.0
        outputs = self._session.run(None, {self._input_name: tensor})

        feature_maps = outputs[self._detection_index]
        anchor_grids = [outputs[index] for index in self._anchor_indices]
        prediction = self._split_for_trace_model(feature_maps, anchor_grids)
        detections = self._non_max_suppression(prediction[0])
        detections = self._scale_detections(detections, gain, pad, source_width, source_height)

        driving_area = 1.0 - outputs[self._driving_index][0, 0]
        lane_lines = outputs[self._lane_index][0, 0]
        driving_area = self._restore_mask(driving_area, pad, model_image.shape[1], model_image.shape[0], source_width, source_height)
        lane_lines = self._restore_mask(lane_lines, pad, model_image.shape[1], model_image.shape[0], source_width, source_height)

        return PerceptionFrame(
            detections=tuple(detections),
            driving_area=driving_area,
            lane_lines=lane_lines,
            source_width=source_width,
            source_height=source_height,
            inference_ms=(time.perf_counter() - started) * 1000.0,
            received_at=time.monotonic(),
        )

    def _letterbox(self, image: np.ndarray) -> tuple[np.ndarray, float, tuple[int, int]]:
        height, width = image.shape[:2]
        ratio = min(self._input_size / height, self._input_size / width)
        resized_width = int(round(width * ratio))
        resized_height = int(round(height * ratio))
        pad_width = (self._input_size - resized_width) / 2
        pad_height = (self._input_size - resized_height) / 2
        left = int(round(pad_width - 0.1))
        right = int(round(pad_width + 0.1))
        top = int(round(pad_height - 0.1))
        bottom = int(round(pad_height + 0.1))
        resized = self._cv2.resize(image, (resized_width, resized_height), interpolation=self._cv2.INTER_LINEAR)
        boxed = self._cv2.copyMakeBorder(
            resized,
            top,
            bottom,
            left,
            right,
            self._cv2.BORDER_CONSTANT,
            value=(114, 114, 114),
        )
        return boxed, ratio, (left, top)

    @staticmethod
    def _sigmoid(values: np.ndarray) -> np.ndarray:
        values = np.asarray(values, dtype=np.float32)
        return 1.0 / (1.0 + np.exp(-np.clip(values, -50.0, 50.0)))

    @classmethod
    def _split_for_trace_model(cls, feature_maps, anchor_grids) -> np.ndarray:
        predictions = []
        strides = (8, 16, 32)
        for index, (feature_map, anchor_grid) in enumerate(zip(feature_maps, anchor_grids)):
            batch, _, height, width = feature_map.shape
            decoded = feature_map.reshape(batch, 3, 85, height, width).transpose(0, 1, 3, 4, 2)
            decoded = cls._sigmoid(decoded)
            grid_x, grid_y = np.meshgrid(np.arange(width), np.arange(height))
            grid = np.stack((grid_x, grid_y), axis=2).reshape(1, 1, height, width, 2).astype(np.float32)
            decoded[..., 0:2] = (decoded[..., 0:2] * 2.0 - 0.5 + grid) * strides[index]
            decoded[..., 2:4] = (decoded[..., 2:4] * 2.0) ** 2 * anchor_grid
            predictions.append(decoded.reshape(batch, -1, 85))
        return np.concatenate(predictions, axis=1)

    def _non_max_suppression(self, prediction: np.ndarray) -> list[tuple[float, float, float, float, float, int]]:
        candidates = prediction[prediction[:, 4] > self._confidence_threshold].copy()
        if not len(candidates):
            return []
        class_scores = candidates[:, 5:] * candidates[:, 4:5]
        class_ids = np.argmax(class_scores, axis=1)
        confidences = class_scores[np.arange(len(class_scores)), class_ids]
        selected = confidences > self._confidence_threshold
        candidates, class_ids, confidences = candidates[selected], class_ids[selected], confidences[selected]
        if not len(candidates):
            return []

        xywh = candidates[:, :4]
        boxes = np.column_stack((
            xywh[:, 0] - xywh[:, 2] / 2.0,
            xywh[:, 1] - xywh[:, 3] / 2.0,
            xywh[:, 0] + xywh[:, 2] / 2.0,
            xywh[:, 1] + xywh[:, 3] / 2.0,
        ))
        if len(boxes) > 30_000:
            top = np.argsort(confidences)[-30_000:]
            boxes, class_ids, confidences = boxes[top], class_ids[top], confidences[top]

        kept: list[int] = []
        for class_id in np.unique(class_ids):
            class_indices = np.flatnonzero(class_ids == class_id)
            order = class_indices[np.argsort(confidences[class_indices])[::-1]]
            while len(order):
                best = int(order[0])
                kept.append(best)
                if len(kept) >= 300:
                    break
                remaining = order[1:]
                if not len(remaining):
                    break
                top_left = np.maximum(boxes[best, :2], boxes[remaining, :2])
                bottom_right = np.minimum(boxes[best, 2:], boxes[remaining, 2:])
                intersection_size = np.maximum(0.0, bottom_right - top_left)
                intersection = intersection_size[:, 0] * intersection_size[:, 1]
                best_area = np.prod(np.maximum(0.0, boxes[best, 2:] - boxes[best, :2]))
                other_areas = np.prod(np.maximum(0.0, boxes[remaining, 2:] - boxes[remaining, :2]), axis=1)
                union = best_area + other_areas - intersection
                iou = np.divide(intersection, union, out=np.zeros_like(intersection), where=union > 0)
                order = remaining[iou <= self._iou_threshold]
            if len(kept) >= 300:
                break

        kept.sort(key=lambda index: float(confidences[index]), reverse=True)
        return [
            (*map(float, boxes[index]), float(confidences[index]), int(class_ids[index]))
            for index in kept[:300]
        ]

    @staticmethod
    def _scale_detections(detections, gain, pad, width, height) -> list[Detection]:
        left, top = pad
        scaled = []
        for x1, y1, x2, y2, confidence, class_id in detections:
            box = (
                float(np.clip((x1 - left) / gain, 0, width)),
                float(np.clip((y1 - top) / gain, 0, height)),
                float(np.clip((x2 - left) / gain, 0, width)),
                float(np.clip((y2 - top) / gain, 0, height)),
            )
            if box[2] <= box[0] or box[3] <= box[1]:
                continue
            label = COCO_CLASSES[class_id] if 0 <= class_id < len(COCO_CLASSES) else f"class {class_id}"
            scaled.append(Detection(box, confidence, class_id, label))
        return scaled

    def _restore_mask(self, mask, pad, input_width, input_height, width, height) -> np.ndarray:
        left, top = pad
        gain = min(input_width / width, input_height / height)
        resized_width = int(round(width * gain))
        resized_height = int(round(height * gain))
        cropped = mask[top:top + resized_height, left:left + resized_width]
        return self._cv2.resize(cropped, (width, height), interpolation=self._cv2.INTER_LINEAR).astype(np.float32)


class PerceptionSystem:
    """Own a roof-height perception camera and process its newest frame off-thread."""

    def __init__(self, session, config: AppConfig):
        self.config = config.perception
        self._session = session
        self._model: YoloPv2Model | None = None
        self._sensor: carla.Sensor | None = None
        self._worker: threading.Thread | None = None
        self._stop = threading.Event()
        self._frame_ready = threading.Event()
        self._frame = LatestImage()
        self._result_lock = threading.Lock()
        self._result: PerceptionFrame | None = None
        self._status = "DISABLED" if not self.config.enabled else "INITIALIZING"
        if not self.config.enabled:
            return

        model_path = Path(self.config.model_path).expanduser()
        if not model_path.is_absolute():
            model_path = Path(__file__).resolve().parents[2] / model_path
        try:
            if not model_path.is_file():
                raise FileNotFoundError(f"Model file not found: {model_path}")
            self._model = YoloPv2Model(model_path, self.config)
            self._create_camera()
            self._status = "WAITING FOR FRONT CAMERA"
            self._worker = threading.Thread(target=self._process_frames, name="yolopv2-inference", daemon=True)
            self._worker.start()
            LOG.info("YOLOPv2 loaded from %s", model_path)
        except Exception as exc:
            self._model = None
            self._status = f"MODEL UNAVAILABLE: {exc}"
            LOG.exception("Could not initialize YOLOPv2 perception")

    def _create_camera(self) -> None:
        blueprint = self._session.world.get_blueprint_library().find("sensor.camera.rgb")
        blueprint.set_attribute("image_size_x", str(self.config.camera_width))
        blueprint.set_attribute("image_size_y", str(self.config.camera_height))
        blueprint.set_attribute("fov", str(self.config.camera_fov))
        blueprint.set_attribute("sensor_tick", str(self.config.sensor_tick_seconds))
        self._sensor = self._session.world.spawn_actor(
            blueprint,
            carla.Transform(
                carla.Location(x=self.config.camera_x, y=self.config.camera_y, z=self.config.camera_z),
                carla.Rotation(pitch=self.config.camera_pitch),
            ),
            attach_to=self._session.ego_vehicle,
            attachment_type=carla.AttachmentType.Rigid,
        )
        self._session.track_sensor(self._sensor)
        self._sensor.listen(self._on_camera_image)

    def _on_camera_image(self, image: carla.Image) -> None:
        if self._stop.is_set():
            return
        self._frame.callback(image)
        self._frame_ready.set()

    def _process_frames(self) -> None:
        last_timestamp = 0.0
        while not self._stop.is_set():
            if not self._frame_ready.wait(timeout=0.5):
                continue
            self._frame_ready.clear()
            image, timestamp = self._frame.read()
            if image is None or timestamp <= last_timestamp:
                continue
            last_timestamp = timestamp
            try:
                result = self._model.infer(image)
            except Exception as exc:
                with self._result_lock:
                    self._status = f"INFERENCE ERROR: {exc}"
                LOG.exception("YOLOPv2 inference failed")
                break
            with self._result_lock:
                self._result = result
                self._status = "LIVE"

    def latest(self) -> tuple[PerceptionFrame | None, str]:
        with self._result_lock:
            result = self._result
            status = self._status
        if result is not None and status == "LIVE" and time.monotonic() - result.received_at > 2.0:
            status = "STALE CAMERA FRAME"
        return result, status

    def close(self) -> None:
        self._stop.set()
        self._frame_ready.set()
        if self._worker is not None:
            self._worker.join(timeout=5.0)
