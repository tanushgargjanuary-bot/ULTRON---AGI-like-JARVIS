# Third-party notices

This file records third-party components that ULTRON includes or derives from.
It does not replace the licence for the ULTRON project itself.

## CryptoJS (vendored, not loaded)

**ULTRON file:** `dashboard/static/crypto-js.min.js`

**What it is:** a minified build of [CryptoJS](https://github.com/brix/crypto-js). The file does not record which version; it is byte-identical to the copy in the upstream MARK-LVI project (`docs/UPSTREAM_RESEARCH.md` lists it among the shared files with an identical blob).

**Licence:** MIT, copyright 2009-2013 Jeff Mott and 2013-2016 Evan Vosberg, as published in the `crypto-js` package on npm. [`CRYPTOJS-LICENSE.txt`](CRYPTOJS-LICENSE.txt) is that licence text. MIT requires the notice to travel with copies of the software, and this file is a copy.

**Is it used?** No. Neither `dashboard/static/app.html` nor `dashboard/static/login.html` loads it: the dashboard now encrypts with the browser's Web Crypto (AES-GCM) and says so in `app.html`. `tests/test_source_hygiene.py` fails if a page starts loading it without this entry being revisited. It is kept, rather than deleted, because it is one of the files the project tracks as identical to upstream; removing it is the owner's decision.

## MediaPipe canonical face geometry

**ULTRON file:** `core/face_model.obj`

**Source file:** `mediapipe/modules/face_geometry/data/canonical_face_model.obj`

**Source repository:** [google-ai-edge/mediapipe](https://github.com/google-ai-edge/mediapipe)

**Inspected source commit:** `e1e239ad86fc9ee4e6c65e573924c45c0176d5c6`

**Source asset blob:** `0e666d1c4e75949d1639c2bcf347a38da4834164`

**Source licence:** Apache License 2.0. The source asset header identifies the MediaPipe Authors and the 2019–2023 copyright period.

**Licence copy:** [`MEDIAPIPE-LICENSE.txt`](MEDIAPIPE-LICENSE.txt) contains the complete root `LICENSE` file from the inspected MediaPipe source commit. It includes the Apache 2.0 terms and the additional third-party notices included by MediaPipe.

### What ULTRON uses

ULTRON keeps the canonical face geometry in `core/face_model.obj`. The asset contains 468 vertices and 898 faces. Its header records the original source and Apache 2.0 licence. The file keeps the geometry and omits texture coordinates because the avatar renderer shades the surface analytically.

The source and ULTRON copies have the same 468 vertices and 898 faces. Their face indices match exactly. ULTRON stores coordinates to four decimal places; the maximum absolute coordinate difference from the inspected source file is 0.00005.

### Separate licence boundaries

- The MediaPipe-derived geometry remains subject to its own Apache 2.0 terms and applicable notices.
- The root [`LICENSE`](../LICENSE) describes the MARK/ULTRON project material under CC BY-NC 4.0. It does not replace the separate licence for this third-party geometry.
- Do not remove the attribution in `core/face_model.obj` or this notice.
- Check a third-party dependency or asset's own licence before copying it into the repository. This notice currently documents the canonical face geometry; it is not a complete inventory of every installed Python package or external service.

This is a provenance and licence record, not legal advice.
