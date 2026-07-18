# EasyNMT v0.9.9.9 Final Release Candidate Fixes

- Loading screen now has a guaranteed minimum display time and is reused on every internal transition.
- Loader content is crisp on iOS: no GPU text rasterization, no mascot scaling animation, correct image aspect ratio.
- Loader is fully opaque and also works before the Welcome Experience.
- Lesson Easy chat covers the whole mobile visual viewport, hides the bottom app bar, and keeps the composer visible above browser controls/keyboard.
- Lesson chat locks and restores the underlying page scroll correctly.
- Cabinet drawer starts closed from first paint and closes before navigation/BFCache restores.
- Active Overview no longer reloads or reopens the drawer.
- Dashboard Easy launcher now consistently shows robot + Easy on desktop and robot only on mobile.
- Notebook Previous/Next controls are after the paper; only one step is displayed at a time to avoid jumpy scrolling.
- Static CSS/JS URLs are cache-busted for Railway and mobile in-app browsers.
