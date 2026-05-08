# GLB Material Editor

Simple Python tool for editing material properties inside `.glb` files.

This editor allows you to quickly:
- open GLB models,
- edit material values,
- and save changes directly back into the model.

No Blender or full 3D software required.

---

# Features

- Open `.glb` files
- Edit material properties:
  - Metallic
  - Roughness
  - Base Color
  - Emissive
  - Alpha Mode
  - Double Sided rendering
- Save changes directly into the GLB
- Lightweight standalone script
- Simple interface

---

# Screenshot

<img width="727" height="478" alt="image" src="https://github.com/user-attachments/assets/4c9e71de-940f-445d-98ac-f64c9f356272" />


---

# Requirements

- Python 3
- pygltflib
- tkinter

Install dependencies:

```bash
pip install pygltflib
```

---

# Usage

Run the script:

```bash
python glb_material_editor.py
```

Steps:
1. Open a `.glb` file
2. Select a material
3. Edit values
4. Save the model

---

# Notes

Visual results may vary depending on:
- renderer,
- lighting,
- environment reflections,
- game engine.

This tool edits material values directly inside the GLB file.

---

# Repository

Small standalone Python script focused on quick GLB material editing.
