# EasyNMT v0.9.9.9 Final Loader Fix

- Loader is hidden on first paint, preventing the old blue flash.
- Loader appears only when a real page load or navigation remains pending for more than 50 ms.
- No artificial 360 ms or 700 ms delay remains.
- Chat, menus, lesson steps, active tabs and other local JavaScript actions do not trigger the full-screen loader.
- Native form validation and uploads remain unchanged.
- Browser back/forward cache immediately clears the loader and transient mobile panels.
