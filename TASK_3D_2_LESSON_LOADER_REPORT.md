# Task 3D.2 Lesson Generation Loader Report

## Problem

Production lesson generation can take about 20–30 seconds. During the server request, the previous page stayed visible without enough feedback, making a healthy request look like a frozen site.

## Resolution

The global page transition layer now switches into a dedicated lesson-generation mode for curriculum lesson routes and start forms. It displays:

- the detected lesson topic;
- a visible animated Easy mascot;
- three staged preparation states;
- a truthful estimated progress bar capped below completion;
- guidance for normal and longer waits.

The overlay blocks duplicate interaction while the request is active and resets safely on browser history restoration.

## Coverage

Detection covers direct curriculum lesson links, start-unit POST forms, forms containing `curriculum_unit_id`, and next-topic actions. The layout is responsive and honors reduced-motion preferences.

## Verification

- JavaScript syntax checked with Node.
- Python modules compiled.
- Complete `unittest` suite executed: 149 tests passed.
- Dedicated loader contract tests added.
