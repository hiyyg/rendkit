from vispy.gloo import gl

from vispy import gloo

from rendkit.glsl import GLSLTemplate, GLSLProgram


class RendtexInputMixin:
    def upload_input(self, program, input_tex):
        program['u_rendtex'] = input_tex
        return program


class IdentityProgram(GLSLProgram, RendtexInputMixin):
    def __init__(self):
        super().__init__(
            GLSLTemplate.fromfile('postprocessing/quad.vert.glsl'),
            GLSLTemplate.fromfile('postprocessing/identity.frag.glsl'))

    def update_uniforms(self, program):
        program['a_uv'] = [(0, 0), (0, 1), (1, 0), (1, 1)]
        program['a_position'] = [(-1, -1), (-1, +1), (+1, -1), (+1, +1)]
        return program


class DownsampleProgram(GLSLProgram, RendtexInputMixin):
    MAX_SCALE = 3
    LANCZOS_KERNELS = [
        [0.44031130485056913, 0.29880437751590694,
         0.04535643028360444, -0.06431646022479595],
        [0.2797564513818748, 0.2310717037833796,
         0.11797652759318597, 0.01107354293249700],
    ]

    def __init__(self, scale: int):
        super().__init__(
            GLSLTemplate.fromfile('postprocessing/quad.vert.glsl'),
            GLSLTemplate.fromfile('postprocessing/ssaa.frag.glsl'))
        assert scale == 2 or scale == 3
        self.scale = scale

    def update_uniforms(self, program):
        program['u_aa_kernel'] = self.LANCZOS_KERNELS[self.scale - 2]
        program['a_uv'] = [(0, 0), (0, 1), (1, 0), (1, 1)]
        program['a_position'] = [(-1, -1), (-1, +1), (+1, -1), (+1, +1)]
        return program

    def upload_input(self, program, input_tex):
        program['u_rendtex'] = input_tex
        program['u_texture_shape'] = input_tex.shape[:2]
        return program


class GammaCorrectionProgram(GLSLProgram, RendtexInputMixin):
    def __init__(self, gamma=2.2):
        super().__init__(
            GLSLTemplate.fromfile('postprocessing/quad.vert.glsl'),
            GLSLTemplate.fromfile('postprocessing/gamma_correction.frag.glsl'))
        self.gamma = gamma

    def update_uniforms(self, program):
        program['a_uv'] = [(0, 0), (0, 1), (1, 0), (1, 1)]
        program['a_position'] = [(-1, -1), (-1, +1), (+1, -1), (+1, +1)]
        program['u_gamma'] = self.gamma
        return program


class ReinhardProgram(GLSLProgram, RendtexInputMixin):
    def __init__(self, thres):
        super().__init__(
            GLSLTemplate.fromfile('postprocessing/quad.vert.glsl'),
            GLSLTemplate.fromfile('postprocessing/reinhard_tonemap.frag.glsl'))
        self.thres = thres

    def update_uniforms(self, program):
        program['a_uv'] = [(0, 0), (0, 1), (1, 0), (1, 1)]
        program['a_position'] = [(-1, -1), (-1, +1), (+1, -1), (+1, +1)]
        program['u_thres'] = self.thres
        return program


class ExposureProgram(GLSLProgram, RendtexInputMixin):
    def __init__(self, exposure):
        super().__init__(
            GLSLTemplate.fromfile('postprocessing/quad.vert.glsl'),
            GLSLTemplate.fromfile('postprocessing/exposure_tonemap.frag.glsl'))
        self.exposure = exposure

    def update_uniforms(self, program):
        program['a_uv'] = [(0, 0), (0, 1), (1, 0), (1, 1)]
        program['a_position'] = [(-1, -1), (-1, +1), (+1, -1), (+1, +1)]
        program['u_exposure'] = self.exposure
        return program


class PostprocessPipeline:
    def __init__(self, size, renderer):
        self.programs = []
        self.compiled = []
        self.render_textures = []
        self.render_framebuffers = []
        self.size = size
        self.renderer = renderer

    def add_program(self, program):
        self.programs.append(program)
        self.compiled.append(program.compile())
        tex, fb = create_rend_target(self.size)
        self.render_textures.append(tex)
        self.render_framebuffers.append(fb)

    def draw(self, input_tex):
        current_tex = input_tex
        for i, program in enumerate(self.programs):
            is_last = i == (len(self.programs) - 1)
            compiled = self.compiled[i]
            program.upload_input(compiled, current_tex)
            gloo.clear(color=True)
            gloo.set_state(depth_test=False)
            if is_last:
                gloo.set_viewport(0, 0, *self.renderer.physical_size)
                compiled.draw(gl.GL_TRIANGLE_STRIP)
            else:
                gloo.set_viewport(0, 0, *self.size)
                with self.render_framebuffers[i]:
                    compiled.draw(gl.GL_TRIANGLE_STRIP)
            current_tex = self.render_textures[i]


def create_rend_target(size):
    shape = (size[1], size[0])
    rendtex = gloo.Texture2D((*shape, 4),
                             interpolation='linear',
                             internalformat='rgba32f')
    fb = gloo.FrameBuffer(rendtex, gloo.RenderBuffer(shape))
    return rendtex, fb
