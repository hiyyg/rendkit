#version 150
#include "utils/math.glsl"
#include "utils/sampling.glsl"
#include "brdf/aittala.glsl"

#define LIGHT_POINT 0
#define LIGHT_DIRECTIONAL 1
#define LIGHT_AMBIENT 2

uniform sampler2D u_diff_map;
uniform sampler2D u_spec_map;
uniform sampler2D u_spec_shape_map;
uniform sampler2D u_normal_map;
uniform vec2 u_sigma_range;
uniform sampler2D u_cdf_sampler;
uniform sampler2D u_pdf_sampler; // Normalization factor for PDF.
uniform vec3 u_cam_pos;
in vec3 v_position;
in vec3 v_normal;
in vec3 v_tangent;
in vec3 v_bitangent;
in vec2 v_uv;

uniform float u_alpha;
#if TPL.num_lights > 0
uniform float u_light_intensity[TPL.num_lights];
uniform vec3 u_light_position[TPL.num_lights];
uniform vec3 u_light_color[TPL.num_lights];
uniform int u_light_type[TPL.num_lights];
#endif

#if TPL.use_radiance_map
uniform samplerCube u_irradiance_map;
uniform samplerCube u_radiance_map;
#endif

const float NUM_LIGHTS = TPL.num_lights;


vec3 compute_irradiance(vec3 N, vec3 L, vec3 light_color) {
  float cosine_term = max(.0, dot(N, L));
  return cosine_term * max(vec3(0.0), light_color);
}

vec2 compute_sample_angles(float sigma, vec2 xi) {
  float phi = 2.0f * M_PI * xi.x;
  float sigma_samp = (sigma - u_sigma_range.x) / (u_sigma_range.y - u_sigma_range.x);
  float theta = texture2D(u_cdf_sampler, vec2(xi.y, sigma_samp)).r;
  return vec2(phi, theta);
}

float get_pdf_value(float sigma, vec2 xi) {
  float sigma_samp = (sigma - u_sigma_range.x) / (u_sigma_range.y - u_sigma_range.x);
  return texture(u_pdf_sampler, vec2(xi.y, sigma_samp)).r;
}


void main() {
  vec3 V = normalize(u_cam_pos - v_position);

  vec3 rho_d = texture2D(u_diff_map, v_uv).rgb;
  vec3 rho_s = texture2D(u_spec_map, v_uv).rgb;
  vec3 specv = texture2D(u_spec_shape_map, v_uv).rgb;

  mat3 TBN = mat3(v_tangent, v_bitangent, v_normal);
  vec3 N = normalize(TBN * texture2D(u_normal_map, v_uv).rgb);

  // Flip normal if back facing.
//  bool is_back_facing = dot(V, v_normal) < 0;
//  if (is_back_facing) {
//    N *= -1;
//  }

  mat2 S = mat2(specv.x, specv.z,
      specv.z, specv.y);

  vec3 total_radiance = vec3(0.0);

  #if TPL.use_radiance_map
  total_radiance += rho_d * texture(u_irradiance_map, N).rgb;

  vec3 specular = vec3(0);
  float sigma = pow(tr(S)/2, -1.0/4.0);
  uint N_SAMPLES = 64u;
  for (uint i = 0u; i < N_SAMPLES; i++) {
    vec2 xi = hammersley(i, N_SAMPLES); // Use psuedo-random point set.
    vec2 sample_angle = compute_sample_angles(sigma, xi);
    float phi = sample_angle.x;
    float theta = sample_angle.y;
    vec3 H = sample_to_world(phi, theta, N);
    vec3 L = reflect(-V, H);
    vec3 light_color = texture(u_radiance_map, L).rgb;
    specular += compute_irradiance(N, L, light_color) *
      aittala_spec_is(N, V, L, rho_s, S, u_alpha, get_pdf_value(sigma, xi));
  }
  specular /= N_SAMPLES;
  total_radiance += specular;
  #endif

  #if TPL.num_lights > 0
  for (int i = 0; i < NUM_LIGHTS; i++) {
    vec3 irradiance = vec3(0);
    if (u_light_type[i] == LIGHT_AMBIENT) {
      irradiance = u_light_intensity[i] * u_light_color[i];
    } else {
      vec3 L;
      float attenuation = 1.0;
      if (u_light_type[i] == LIGHT_POINT) {
        L = u_light_position[i] - v_position;
        attenuation = 1.0 / dot(L, L);
        L = normalize(L);
      } else if (u_light_type[i] == LIGHT_DIRECTIONAL) {
        L = normalize(u_light_position[i]);
      } else {
        continue;
      }
      bool is_light_visible = dot(L, N) >= 0;
      if (is_light_visible) {
        irradiance = compute_irradiance(N, L, u_light_intensity[i] * u_light_color[i]);
        total_radiance += aittala_spec(N, V, L, rho_s, S, u_alpha) * irradiance;
      }
    }
    total_radiance += rho_d * irradiance;
  }
  #endif

  gl_FragColor = vec4(max(vec3(.0), total_radiance), 1.0);    // rough gamma
}
