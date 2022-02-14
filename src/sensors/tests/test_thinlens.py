import pytest
import drjit as dr
import mitsuba as mi


def create_camera(o, d, fov=34, fov_axis="x", s_open=1.5, s_close=5, aperture=0.1, focus_dist=15, near_clip=1.0):
    t = [o[0] + d[0], o[1] + d[1], o[2] + d[2]]

    camera_dict = {
        "type": "thinlens",
        "near_clip": near_clip,
        "far_clip": 35.0,
        "focus_distance": focus_dist,
        "aperture_radius": aperture,
        "fov": fov,
        "fov_axis": fov_axis,
        "shutter_open": s_open,
        "shutter_close": s_close,
        "to_world": mi.ScalarTransform4f.look_at(
            origin=o,
            target=t,
            up=[0, 1, 0]
        ),
        "film": {
            "type": "hdrfilm",
            "width": 512,
            "height": 256,
        }
    }

    return mi.load_dict(camera_dict)


origins = [[1.0, 0.0, 1.5], [1.0, 4.0, 1.5]]
directions = [[0.0, 0.0, 1.0], [1.0, 0.0, 0.0]]


@pytest.mark.parametrize("origin", origins)
@pytest.mark.parametrize("direction", directions)
@pytest.mark.parametrize("s_open", [0.0, 1.5])
@pytest.mark.parametrize("s_time", [0.0, 3.0])
def test01_create(variant_scalar_rgb, origin, direction, s_open, s_time):
    camera = create_camera(
        origin, direction, s_open=s_open, s_close=s_open + s_time)

    assert dr.allclose(camera.near_clip(), 1)
    assert dr.allclose(camera.far_clip(), 35)
    assert dr.allclose(camera.focus_distance(), 15)
    assert dr.allclose(camera.shutter_open(), s_open)
    assert dr.allclose(camera.shutter_open_time(), s_time)
    assert camera.needs_aperture_sample()
    assert camera.bbox() == mi.BoundingBox3f(origin, origin)
    assert dr.allclose(camera.world_transform().matrix,
                       mi.Transform4f.look_at(origin, mi.Vector3f(origin) + direction, [0, 1, 0]).matrix)


@pytest.mark.parametrize("origin", origins)
@pytest.mark.parametrize("direction", directions)
@pytest.mark.parametrize("aperture_rad", [0.01, 0.1, 0.25])
@pytest.mark.parametrize("focus_dist", [15, 25])
def test02_sample_ray(variants_vec_spectral, origin, direction, aperture_rad, focus_dist):
    """Check the correctness of the sample_ray() method"""

    near_clip = 1.0
    cam = create_camera(origin, direction, aperture=aperture_rad, focus_dist=focus_dist, near_clip=near_clip)

    time = 0.0
    wav_sample = [0.5, 0.33, 0.1]
    pos_sample = [[0.2, 0.1, 0.2], [0.6, 0.9, 0.2]]
    aperture_sample = [0.5, 0.5]

    ray, spec_weight = cam.sample_ray(
        time, wav_sample, pos_sample, aperture_sample)

    # Importance sample wavelength and weight
    wav, spec = mi.sample_rgb_spectrum(mi.sample_shifted(wav_sample))

    assert dr.allclose(ray.wavelengths, wav)
    assert dr.allclose(spec_weight, spec)
    assert dr.allclose(ray.time, time)

    inv_z = dr.rcp((cam.world_transform().inverse() @ ray.d).z)
    o = mi.Point3f(origin) + near_clip * inv_z * mi.Vector3f(ray.d)
    assert dr.allclose(ray.o, o, atol=1e-4)


    # Check that a [0.5, 0.5] position_sample and [0.5, 0.5] aperture_sample
    # generates a ray that points in the camera direction

    ray, _ = cam.sample_ray(0, 0, [0.5, 0.5], [0.5, 0.5])
    assert dr.allclose(ray.d, direction, atol=1e-7)

    # ----------------------------------------
    # Check correctness of aperture sampling

    pos_sample = [0.5, 0.5]
    aperture_sample = [[0.9, 0.4, 0.2], [0.6, 0.9, 0.7]]
    ray, _ = cam.sample_ray(time, wav_sample, pos_sample, aperture_sample)

    ray_centered, _ = cam.sample_ray(time, wav_sample, pos_sample, [0.5, 0.5])

    trafo = mi.Transform4f.look_at(origin, mi.Vector3f(origin) + mi.Vector3f(direction), [0, 1, 0])
    tmp = aperture_rad * mi.warp.square_to_uniform_disk_concentric(aperture_sample)
    aperture_v = trafo @ mi.Vector3f(tmp.x, tmp.y, 0)

    inv_z_centered = dr.rcp((cam.world_transform().inverse() @ ray_centered.d).z)
    o_centered = ray_centered.o - near_clip * inv_z_centered * mi.Vector3f(ray_centered.d)
    inv_z = dr.rcp((cam.world_transform().inverse() @ ray.d).z)
    o = o_centered + aperture_v + near_clip * inv_z * mi.Vector3f(ray.d)
    assert dr.allclose(ray.o, o, atol=1e-4)
    assert dr.allclose(ray.d, dr.normalize(ray_centered.d * focus_dist - aperture_v), atol=1e-4)


@pytest.mark.parametrize("origin", origins)
@pytest.mark.parametrize("direction", directions)
@pytest.mark.parametrize("aperture_rad", [0.01, 0.1, 0.25])
@pytest.mark.parametrize("focus_dist", [15, 25])
def test03_sample_ray_diff(variants_vec_spectral, origin, direction, aperture_rad, focus_dist):
    """Check the correctness of the sample_ray_differential() method"""

    near_clip = 1.0
    cam = create_camera(origin, direction, aperture=aperture_rad, focus_dist=focus_dist, near_clip=near_clip)

    time = 0.5
    wav_sample = [0.5, 0.33, 0.1]
    pos_sample = [[0.2, 0.1, 0.2], [0.6, 0.9, 0.2]]
    aperture_sample = [0.5, 0.5]

    ray, spec_weight = cam.sample_ray_differential(
        time, wav_sample, pos_sample, aperture_sample)

    # Importance sample wavelength and weight
    wav, spec = mi.sample_rgb_spectrum(mi.sample_shifted(wav_sample))

    assert dr.allclose(ray.wavelengths, wav)
    assert dr.allclose(spec_weight, spec)
    assert dr.allclose(ray.time, time)

    inv_z = dr.rcp((cam.world_transform().inverse() @ ray.d).z)
    o = mi.Point3f(origin) + near_clip * inv_z * mi.Vector3f(ray.d)
    assert dr.allclose(ray.o, o, atol=1e-4)

    # ----------------------------------------_
    # Check that the derivatives are orthogonal

    assert dr.allclose(dr.dot(ray.d_x - ray.d, ray.d_y - ray.d), 0, atol=1e-7)

    # Check that a [0.5, 0.5] position_sample and [0.5, 0.5] aperture_sample
    # generates a ray that points in the camera direction

    ray_center, _ = cam.sample_ray_differential(0, 0, [0.5, 0.5], [0.5, 0.5])
    assert dr.allclose(ray_center.d, direction, atol=1e-7)

    # ----------------------------------------
    # Check correctness of the ray derivatives

    aperture_sample = [[0.9, 0.4, 0.2], [0.6, 0.9, 0.7]]
    ray_center, _ = cam.sample_ray_differential(0, 0, [0.5, 0.5], aperture_sample)

    # Deltas in screen space
    dx = 1.0 / cam.film().crop_size().x
    dy = 1.0 / cam.film().crop_size().y

    # Sample the rays by offsetting the position_sample with the deltas (aperture centered)
    ray_dx, _ = cam.sample_ray_differential(0, 0, [0.5 + dx, 0.5], aperture_sample)
    ray_dy, _ = cam.sample_ray_differential(0, 0, [0.5, 0.5 + dy], aperture_sample)

    assert dr.allclose(ray_dx.d, ray_center.d_x)
    assert dr.allclose(ray_dy.d, ray_center.d_y)

    # --------------------------------------
    # Check correctness of aperture sampling

    pos_sample = [0.5, 0.5]
    aperture_sample = [[0.9, 0.4, 0.2], [0.6, 0.9, 0.7]]
    ray, _ = cam.sample_ray(time, wav_sample, pos_sample, aperture_sample)

    ray_centered, _ = cam.sample_ray(time, wav_sample, pos_sample, [0.5, 0.5])

    trafo = mi.Transform4f.look_at(origin, mi.Vector3f(origin) + mi.Vector3f(direction), [0, 1, 0])
    tmp = mi.warp.square_to_uniform_disk_concentric(aperture_sample)
    aperture_v = trafo @ (aperture_rad * mi.Vector3f(tmp.x, tmp.y, 0))

    inv_z_centered = dr.rcp((cam.world_transform().inverse() @ ray_centered.d).z)
    o_centered = ray_centered.o - near_clip * inv_z_centered * mi.Vector3f(ray_centered.d)
    inv_z = dr.rcp((cam.world_transform().inverse() @ ray.d).z)
    o = o_centered + aperture_v + near_clip * inv_z * mi.Vector3f(ray.d)
    assert dr.allclose(ray.o, o, atol=1e-4)
    assert dr.allclose(ray.d, dr.normalize(ray_centered.d * focus_dist - aperture_v), atol=1e-4)


@pytest.mark.parametrize("origin", [[1.0, 0.0, 1.5]])
@pytest.mark.parametrize("direction", [[0.0, 0.0, 1.0], [1.0, 0.0, 0.0]])
@pytest.mark.parametrize("fov", [34, 80])
def test04_fov_axis(variants_vec_spectral, origin, direction, fov):
    """
    Check that sampling position_sample at the extremities of the unit square
    along the fov_axis should generate a ray direction that make angle of fov/2
    with the camera direction.
    """

    def check_fov(camera, sample):
        # aperture position at the center
        ray, _ = camera.sample_ray(0, 0, sample, [0.5, 0.5])
        assert dr.allclose(dr.acos(dr.dot(ray.d, direction))
                           * 180 / dr.Pi, fov / 2)

    # In the configuration, aspect==1.5, so 'larger' should give the 'x'-axis
    for fov_axis in ['x', 'larger']:
        camera = create_camera(origin, direction, fov=fov, fov_axis=fov_axis)
        for sample in [[0.0, 0.5], [1.0, 0.5]]:
            check_fov(camera, sample)

    # In the configuration, aspect==1.5, so 'smaller' should give the 'y'-axis
    for fov_axis in ['y', 'smaller']:
        camera = create_camera(origin, direction, fov=fov, fov_axis=fov_axis)
        for sample in [[0.5, 0.0], [0.5, 1.0]]:
            check_fov(camera, sample)

    # Check the 4 corners for the `diagonal` case
    camera = create_camera(origin, direction, fov=fov, fov_axis='diagonal')
    for sample in [[0.0, 0.0], [0.0, 1.0], [1.0, 0.0], [1.0, 1.0]]:
        check_fov(camera, sample)


def test05_spectrum_sampling(variants_vec_spectral):
    # Check RGB wavelength sampling
    camera = mi.load_dict({
        "type": "thinlens",
        "aperture_radius": 1.0,
    })
    wavelengths, _ =  camera.sample_wavelengths(dr.zero(mi.SurfaceInteraction3f), mi.Float([0.1, 0.4, 0.9]))
    assert (dr.all_nested((wavelengths >= mi.MI_CIE_MIN) & (wavelengths <= mi.MI_CIE_MAX)))

    # Check custom SRF wavelength sampling
    camera = mi.load_dict({
        "type": "thinlens",
        "aperture_radius": 1.0,
        "srf": {
            "type": 'spectrum',
            "value": [(1200,1.0), (1400,1.0)]
        }
    })
    wavelengths, _ =  camera.sample_wavelengths(dr.zero(mi.SurfaceInteraction3f), mi.Float([0.1, 0.4, 0.9]))
    assert (dr.all_nested((wavelengths >= 1200) & (wavelengths <= 1400)))

    # Check error if double SRF is defined
    with pytest.raises(RuntimeError, match=r'Sensor\(\)'):
        camera = mi.load_dict({
            'type': 'thinlens',
            'aperture_radius': 1.0,
            'srf': {
                'type': 'spectrum',
                'value': [(1200,1.0), (1400,1.0)]
            },
            'film': {
                'type': 'specfilm',
                'srf_test': {
                    'type': 'spectrum',
                    'value': [(34,1.0),(79,1.0),(120,1.0)]
                }
            }
        })
