from datetime import datetime
import unittest

import main


class AISafeAgentWeatherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.module = main.load_ai_safe_agent_module()

    def test_kma_categories_are_normalized_into_hourly_point(self):
        point = self.module._rain_hourly_points(datetime(2026, 7, 16, 12))[0]
        items = [
            {"category": "T1H", "obsrValue": "31.2"},
            {"category": "REH", "obsrValue": "78"},
            {"category": "WSD", "obsrValue": "4.3"},
            {"category": "VEC", "obsrValue": "225"},
            {"category": "PTY", "obsrValue": "1"},
        ]

        self.module._set_weather_items(point, items, "obsrValue")

        self.assertEqual(point["temperature_c"], 31.2)
        self.assertEqual(point["humidity_pct"], 78.0)
        self.assertEqual(point["wind_speed_ms"], 4.3)
        self.assertEqual(point["wind_direction_deg"], 225.0)
        self.assertEqual(point["precipitation_type_label"], "비")

    def test_forecast_keeps_observation_and_fills_missing_fields(self):
        point = {"temperature_c": 29.5, "precipitation_probability_pct": None}

        self.module._set_weather_item(point, "T1H", "27", overwrite=False)
        self.module._set_weather_item(point, "POP", "60", overwrite=False)

        self.assertEqual(point["temperature_c"], 29.5)
        self.assertEqual(point["precipitation_probability_pct"], 60.0)

    def test_missing_rain_is_not_converted_to_zero(self):
        point = self.module._rain_hourly_points(datetime(2026, 7, 16, 12))[0]

        self.assertEqual(point["value"], "-")
        self.assertIsNone(point["value_mm"])
        self.assertIsNone(self.module._rn1_value([], "fcstValue"))

        self.module._set_rain_hourly_value({0: point}, 0, None, "forecast")
        self.assertEqual(point["source"], "none")

        self.module._set_rain_hourly_value({0: point}, 0, "강수없음", "forecast")
        self.assertEqual(point["value_mm"], 0.0)
        self.assertEqual(point["source"], "forecast")


    def test_chart_has_dual_axes_icons_and_missing_value_segments(self):
        html = main.build_html()

        self.assertIn("safe-agent-chart-axis", html)
        self.assertIn("weatherIcon(item)", html)
        self.assertIn("weatherSegments(points", html)
        self.assertIn("강수 자료 없음", html)
        self.assertIn("height=124", html)


    def test_report_instruction_is_exception_first_and_actionable(self):
        instruction = self.module.system_instruction()

        self.assertIn("한 문장, 한 줄", instruction)
        self.assertIn("특이사항:", instruction)
        self.assertIn("지금 할 일:", instruction)
        self.assertIn("지금 바로 실행할 수 있는 구체적인 행동", instruction)
        self.assertIn("시간순으로 읽어 주거나", instruction)
        self.assertNotIn("반드시 '1. 현재 상황'", instruction)


    def test_report_output_is_one_line_or_actionable_two_lines(self):
        safe = self.module.normalize_report_output("", "특이사항: 위험 없음. 지금 할 일: 조치 불필요.")
        self.assertEqual(safe, "현재 즉시 대응이 필요한 특이사항은 없습니다.")
        self.assertNotIn("\n", safe)

        model_safe = self.module.normalize_report_output("", "현재와 예상 기상이 겹치지 않습니다.")
        self.assertEqual(model_safe, "현재 즉시 대응이 필요한 특이사항은 없습니다.")

        forced_safe = self.module.normalize_report_output(
            "[보고서 출력 제어]\n- 즉시 알릴 특이사항: 없음",
            "특이사항: 주변에 침수 흔적이 있습니다.",
        )
        self.assertEqual(forced_safe, "현재 즉시 대응이 필요한 특이사항은 없습니다.")

        forced_risk = self.module.normalize_report_output(
            "[보고서 출력 제어]\n- 즉시 알릴 특이사항: 있음\n- 핵심: 비와 주변 침수 이력이 겹침",
            "현재 즉시 대응이 필요한 특이사항은 없습니다.",
        )
        self.assertEqual(len(forced_risk.splitlines()), 2)
        self.assertIn("비와 주변 침수 이력이 겹침", forced_risk)
        self.assertIn("지하공간과 하천변에서 벗어나", forced_risk)


        risk = self.module.normalize_report_output(
            "강한 비가 이어지고 주변에 침수 흔적이 있습니다.",
            "특이사항: 강한 비와 침수 이력이 있어 특별히 주의해야 합니다.",
        )
        self.assertEqual(len(risk.splitlines()), 2)
        self.assertTrue(risk.startswith("특이사항:"))
        self.assertIn("지금 할 일:", risk)
        self.assertIn("지하공간과 하천변에서 벗어나", risk)


    def test_prompt_uses_actual_time_and_additional_weather(self):
        point = self.module._rain_hourly_points(datetime(2026, 7, 16, 12))[0]
        point.update({
            "value": "3mm",
            "value_mm": 3.0,
            "temperature_c": 30.0,
            "humidity_pct": 80.0,
            "wind_speed_ms": 5.0,
            "precipitation_type_label": "비",
            "precipitation_probability_pct": 70.0,
        })
        rain = {
            "rain_current": "3mm",
            "rain_1h_after": "4mm",
            "rain_2h_after": "2mm",
            "rain_3h_after": "0mm",
            "rain_6h_accum": "12mm",
            "rain_hourly": [point],
        }

        context, _ = self.module.build_prompt_context(
            37.5665,
            126.978,
            rain,
            self.module.DisasterKnowledgeBase.empty(),
        )

        self.assertIn("[기상 시간 흐름", context)
        self.assertIn("07-16 12:00", context)
        self.assertIn("30°C", context)
        self.assertIn("습도 80%", context)
        self.assertIn("강수확률 70%", context)


if __name__ == "__main__":
    unittest.main()
