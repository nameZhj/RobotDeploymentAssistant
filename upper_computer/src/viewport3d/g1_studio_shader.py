# @file: src/viewport3d/g1_studio_shader.py
# @brief: GLSL 120 3-point + hemisphere studio metallic shader matching official G1 silver-grey & charcoal look.
# @exports: G1StudioShader

from __future__ import annotations

import math
from typing import Tuple
import numpy as np

_VERT_SRC = """
#version 120
varying vec3 vEyePos;
varying vec3 vNormal;
void main() {
    vec4 eye = gl_ModelViewMatrix * gl_Vertex;
    vEyePos = eye.xyz;
    vNormal = normalize(gl_NormalMatrix * gl_Normal);
    gl_Position = gl_ModelViewProjectionMatrix * gl_Vertex;
}
"""

_FRAG_SRC = """
#version 120
varying vec3 vEyePos;
varying vec3 vNormal;

uniform vec3 uBaseColor;
uniform float uMetallic;
uniform float uRoughness;
uniform vec3 uEmissive;
uniform vec3 uKeyDir;
uniform vec3 uFillDir;
uniform vec3 uRimDir;
uniform vec3 uUpDir;

void main() {
    vec3 N = normalize(gl_FrontFacing ? vNormal : -vNormal);
    vec3 V = normalize(-vEyePos);

    float upDot = clamp(0.5 + 0.5 * dot(N, uUpDir), 0.0, 1.0);
    vec3 hemiEnv = mix(vec3(0.24, 0.27, 0.32), vec3(0.76, 0.79, 0.84), upDot);

    float ndotlKey = max(dot(N, uKeyDir), 0.0);
    float ndotlFill = max(dot(N, uFillDir), 0.0);
    float ndotlRim = max(dot(N, uRimDir), 0.0);

    vec3 Hkey = normalize(uKeyDir + V);
    vec3 Hfill = normalize(uFillDir + V);
    vec3 Hrim = normalize(uRimDir + V);

    float shininess = pow(2.0, 9.0 * (1.0 - clamp(uRoughness, 0.05, 0.95)) + 1.0);
    float specScale = (0.045 * shininess + 0.12) * (1.0 - 0.55 * uRoughness);

    float specKey = pow(max(dot(N, Hkey), 0.0), shininess) * specScale;
    float specFill = pow(max(dot(N, Hfill), 0.0), max(8.0, shininess * 0.5)) * specScale * 0.38;
    float specRim = pow(max(dot(N, Hrim), 0.0), max(10.0, shininess * 0.6)) * specScale * 0.52;

    float fresnel = pow(1.0 - max(dot(N, V), 0.0), 4.0);
    vec3 F0 = mix(vec3(0.04), uBaseColor, uMetallic);
    vec3 F = F0 + (vec3(1.0) - F0) * fresnel;

    vec3 R = reflect(-V, N);
    float envBand = smoothstep(-0.35, 0.85, dot(R, uUpDir));
    vec3 studioEnv = mix(vec3(0.22, 0.25, 0.30), vec3(0.95, 0.97, 1.00), envBand);

    vec3 diffuseCol = uBaseColor * (1.0 - 0.48 * uMetallic);
    vec3 directDiff = diffuseCol * (
        ndotlKey * vec3(0.98, 0.97, 0.95) * 0.78 +
        ndotlFill * vec3(0.48, 0.54, 0.62) * 0.42 +
        ndotlRim * vec3(0.55, 0.60, 0.68) * 0.28
    );
    vec3 ambientDiff = diffuseCol * hemiEnv * 0.52;
    vec3 directSpec = F * (
        specKey * vec3(1.05, 1.03, 1.00) +
        specFill * vec3(0.65, 0.72, 0.82) +
        specRim * vec3(0.75, 0.80, 0.88)
    );
    vec3 metalRefl = uBaseColor * studioEnv * uMetallic * (0.28 + 0.48 * fresnel) * (1.0 - 0.45 * uRoughness);
    vec3 rimGlow = vec3(0.75, 0.82, 0.90) * pow(1.0 - max(dot(N, V), 0.0), 3.0) * 0.14;

    vec3 col = ambientDiff + directDiff + directSpec + metalRefl + rimGlow + uEmissive;
    col = (col / (col + vec3(0.32))) * 1.24;
    gl_FragColor = vec4(clamp(col, 0.0, 1.0), 1.0);
}
"""


def _norm3(v: Tuple[float, float, float]) -> np.ndarray:
    arr = np.asarray(v, dtype=np.float32)
    n = float(np.linalg.norm(arr))
    return arr / n if n > 1e-6 else np.array([0.0, 0.0, 1.0], dtype=np.float32)


class G1StudioShader:
    """Manages optional GLSL studio lighting program with graceful fixed-function fallback."""

    def __init__(self) -> None:
        self.program: int = 0
        self.available: bool = False
        self._uniforms: dict[str, int] = {}
        self._w_key = _norm3((0.45, -0.68, 0.82))
        self._w_fill = _norm3((-0.78, 0.42, 0.36))
        self._w_rim = _norm3((0.20, 0.85, 0.52))
        self._w_up = np.array([0.0, 0.0, 1.0], dtype=np.float32)

    def initialize(self, gl_mod) -> bool:
        """Compile and link GLSL 120 program; returns False safely on unsupported drivers."""
        self.release(gl_mod)
        needed = ("glCreateShader", "glShaderSource", "glCompileShader", "glCreateProgram", "glAttachShader", "glLinkProgram", "glUseProgram", "glGetUniformLocation")
        if not all(hasattr(gl_mod, fn) for fn in needed):
            self.available = False
            return False
        vs = fs = prog = 0
        try:
            vs = int(gl_mod.glCreateShader(gl_mod.GL_VERTEX_SHADER))
            gl_mod.glShaderSource(vs, _VERT_SRC)
            gl_mod.glCompileShader(vs)
            if not gl_mod.glGetShaderiv(vs, gl_mod.GL_COMPILE_STATUS):
                raise RuntimeError("vs compile failed")

            fs = int(gl_mod.glCreateShader(gl_mod.GL_FRAGMENT_SHADER))
            gl_mod.glShaderSource(fs, _FRAG_SRC)
            gl_mod.glCompileShader(fs)
            if not gl_mod.glGetShaderiv(fs, gl_mod.GL_COMPILE_STATUS):
                raise RuntimeError("fs compile failed")

            prog = int(gl_mod.glCreateProgram())
            gl_mod.glAttachShader(prog, vs)
            gl_mod.glAttachShader(prog, fs)
            gl_mod.glLinkProgram(prog)
            if not gl_mod.glGetProgramiv(prog, gl_mod.GL_LINK_STATUS):
                raise RuntimeError("program link failed")

            gl_mod.glDeleteShader(vs)
            gl_mod.glDeleteShader(fs)
            self.program = prog
            for name in ("uBaseColor", "uMetallic", "uRoughness", "uEmissive", "uKeyDir", "uFillDir", "uRimDir", "uUpDir"):
                self._uniforms[name] = int(gl_mod.glGetUniformLocation(prog, name))
            self.available = True
            return True
        except Exception:
            for sid in (vs, fs):
                if sid and hasattr(gl_mod, "glDeleteShader"):
                    try:
                        gl_mod.glDeleteShader(sid)
                    except Exception:
                        pass
            if prog and hasattr(gl_mod, "glDeleteProgram"):
                try:
                    gl_mod.glDeleteProgram(prog)
                except Exception:
                    pass
            self.program = 0
            self.available = False
            return False

    def begin(self, gl_mod, view_mat4: np.ndarray) -> bool:
        """Bind shader program and upload eye-space studio light vectors from current view matrix."""
        if not self.available or not self.program:
            return False
        try:
            gl_mod.glUseProgram(self.program)
            rot = np.asarray(view_mat4[:3, :3], dtype=np.float32)
            for uname, wdir in (("uKeyDir", self._w_key), ("uFillDir", self._w_fill), ("uRimDir", self._w_rim), ("uUpDir", self._w_up)):
                loc = self._uniforms.get(uname, -1)
                if loc >= 0:
                    ed = rot @ wdir
                    n = float(math.sqrt(float(ed[0] * ed[0] + ed[1] * ed[1] + ed[2] * ed[2]))) or 1.0
                    gl_mod.glUniform3f(loc, float(ed[0] / n), float(ed[1] / n), float(ed[2] / n))
            return True
        except Exception:
            self.available = False
            self.end(gl_mod)
            return False

    def set_material(
        self, gl_mod, base_rgb: Tuple[float, float, float], metallic: float,
        roughness: float, emissive: Tuple[float, float, float] = (0.0, 0.0, 0.0),
    ) -> None:
        if not self.available:
            return
        if self._uniforms.get("uBaseColor", -1) >= 0:
            gl_mod.glUniform3f(self._uniforms["uBaseColor"], *base_rgb)
        if self._uniforms.get("uMetallic", -1) >= 0:
            gl_mod.glUniform1f(self._uniforms["uMetallic"], float(metallic))
        if self._uniforms.get("uRoughness", -1) >= 0:
            gl_mod.glUniform1f(self._uniforms["uRoughness"], float(roughness))
        if self._uniforms.get("uEmissive", -1) >= 0:
            gl_mod.glUniform3f(self._uniforms["uEmissive"], *emissive)

    @staticmethod
    def end(gl_mod) -> None:
        if hasattr(gl_mod, "glUseProgram"):
            try:
                gl_mod.glUseProgram(0)
            except Exception:
                pass

    def release(self, gl_mod) -> None:
        self._uniforms.clear()
        if self.program and hasattr(gl_mod, "glDeleteProgram"):
            try:
                gl_mod.glDeleteProgram(self.program)
            except Exception:
                pass
        self.program = 0
        self.available = False
