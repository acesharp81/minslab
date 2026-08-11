# RHWP vendored runtime provenance

- Source: https://github.com/edwardkim/rhwp
- Studio distribution: https://edwardkim.github.io/rhwp/
- Embedded package: `@rhwp/editor@0.8.2`
- Source commit: `2dced7bfe10c6597cead634264c7c1781c01f1e7`
- License: MIT (`LICENSE` in this directory)
- Vendored: 2026-08-11

Original distribution SHA-256:

- Studio JS: `4e982de9afef7a75076c055142249b33ea5ca2660a5b8345fa778bf4d25e019e`
- Studio CSS: `e157fa951af862bdc37fcd2f0318e88dc0f17b591e1b36271b9ef75186e866b6`
- npm tarball: `e2618db88ffe0db5ebb6c6ae2c860bcc878188fae2ced51a1e7febaea7c2e1fc`

AIWorks local changes:

- `/rhwp/` asset URLs were rebased to `/poc/aiworks/rhwp/` for same-origin hosting.
- `disableExternalWebFonts` defaults to true; document rendering does not request external font CDNs.
- `selection-edit-v1` exposes native selection text and atomic, Undo-capable replacement to the host Orchestrator.
- The custom Studio and WASM were rebuilt from the same source with wasm-pack 0.15.0; 641 upstream Studio contract tests passed.
- The Studio, editor adapter, WASM and common Korean fonts are served by AIWorks itself.

Current vendored artifact SHA-256:

- Studio JS: `5251dcee72691a93ef6e686722bd7314ccf58e414107aeb9ef60c0c8f55f6b47`
- Studio CSS: `8f9ddf23a5a5805fe458875050bd65ee2a99f211a4b1f26166a01b59b20c4497`
- WASM: `1f6ab50679a1172a305f06c74b8c314e72a167f34160d762dc18b994f0864bc2`
- AIWorks editor adapter: `774f34ab7f879bd2d647072f87d78b061808a820fb068006bc761476f9673baf`
