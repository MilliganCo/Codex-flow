"""Run with: python -m tools.smoke"""

import unittest


CHECKS = (
    "tests.test_model.ModelTests.test_rooted_connected_acyclic_segment_graph",
    "tests.test_render.RenderTests.test_crossing_tubes_occlude_correctly_in_both_draw_orders",
    "tests.test_render.RenderTests.test_hyperplane_rotation_changes_frames_in_all_planes",
    "tests.test_app.AppTests.test_full_loop_modes_rotation_help_animation_export_and_exit",
    "tests.test_app.AppTests.test_resize_including_minimum_and_restoration",
    "tests.test_cli.CliTests.test_headless_all_modes_exact_bytes_and_determinism",
    "tests.test_cli.CliTests.test_noninteractive_view_exits_with_actionable_message",
    "tests.test_cli.CliTests.test_help_and_version_start_and_exit_cleanly",
)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromNames(CHECKS)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
