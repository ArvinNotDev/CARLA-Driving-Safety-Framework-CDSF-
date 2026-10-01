from carla_drive.sensors.parking import beep_interval_ms, parking_fill


def test_parking_bar_fill_grows_as_obstacle_gets_closer():
    assert parking_fill(None, 6.0) == 0.0
    assert parking_fill(6.0, 6.0) == 0.0
    assert parking_fill(3.0, 6.0) == 0.5
    assert parking_fill(0.0, 6.0) == 1.0


def test_beep_interval_gets_shorter_toward_critical_distance():
    assert beep_interval_ms(3.0, 2.0, 0.6, 900, 120) is None
    assert beep_interval_ms(2.0, 2.0, 0.6, 900, 120) == 900
    assert beep_interval_ms(1.3, 2.0, 0.6, 900, 120) < 900
    assert beep_interval_ms(0.4, 2.0, 0.6, 900, 120) == 120
