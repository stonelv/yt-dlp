#!/usr/bin/env python3
"""Test script for FFmpegLoudnormPP"""

import sys
sys.path.insert(0, '/Users/lvzhe/github/GSB/yt-dlp')

from yt_dlp.postprocessor import FFmpegLoudnormPP


def test_import():
    """Test that FFmpegLoudnormPP can be imported"""
    print('=== Testing Import ===')
    print(f'FFmpegLoudnormPP imported: {FFmpegLoudnormPP is not None}')
    print(f'pp_key: {FFmpegLoudnormPP.pp_key()}')


def test_class_attributes():
    """Test class attributes"""
    print()
    print('=== Testing Class Attributes ===')
    print(f'DEFAULT_TARGET_LOUDNESS: {FFmpegLoudnormPP.DEFAULT_TARGET_LOUDNESS}')
    print(f'DEFAULT_TARGET_LRA: {FFmpegLoudnormPP.DEFAULT_TARGET_LRA}')
    print(f'DEFAULT_TARGET_PEAK: {FFmpegLoudnormPP.DEFAULT_TARGET_PEAK}')


def test_parse_loudnorm_output():
    """Test _parse_loudnorm_output method"""
    print()
    print('=== Testing _parse_loudnorm_output ===')
    
    sample_stderr = '''
ffmpeg version 6.1.1 Copyright (c) 2000-2023 the FFmpeg developers
Input #0, mov,mp4,m4a,3gp,3g2,mj2, from 'test.mp4':
  Metadata:
    major_brand     : isom
    minor_version   : 512
    compatible_brands: isomiso2avc1mp41
    encoder         : Lavf60.3.100
  Duration: 00:00:10.03, start: 0.000000, bitrate: 1234 kb/s
  Stream #0:0[0x1](und): Video: h264 (High) (avc1 / 0x31637661), yuv420p(tv, progressive), 1920x1080 [SAR 1:1 DAR 16:9], 1100 kb/s, 30 fps, 30 tbr, 16k tbn (default)
  Stream #0:1[0x2](und): Audio: aac (LC) (mp4a / 0x6134706D), 44100 Hz, stereo, fltp, 128 kb/s (default)
Output #0, null, to 'pipe:':
  Metadata:
    encoder         : Lavf60.3.100
  Stream #0:0: Audio: pcm_s16le, 44100 Hz, stereo, s16, 1411 kb/s
Stream mapping:
  Stream #0:1 -> #0:0 (aac (native) -> pcm_s16le (native))
Press [q] to stop, [?] for help
size=N/A time=00:00:10.00 bitrate=N/A speed= 200x    
video:0kB audio:1722kB subtitle:0kB other streams:0kB global headers:0kB muxing overhead: unknown
[Parsed_loudnorm_0 @ 0x7ff8b8c05ac0] 
{
    "input_i" : -18.5,
    "input_tp" : -1.2,
    "input_lra" : 8.3,
    "input_thresh" : -28.7,
    "output_i" : -24.0,
    "output_tp" : -2.0,
    "output_lra" : 7.0,
    "output_thresh" : -34.5,
    "normalization_type" : "dynamic",
    "target_offset" : 0.5
}
'''

    pp = FFmpegLoudnormPP(None)
    result = pp._parse_loudnorm_output(sample_stderr)
    
    assert result is not None, 'Failed to parse loudnorm output'
    print(f'Parsed result: {result}')
    print(f'  measured_I: {result["measured_I"]} (expected: -18.5)')
    print(f'  measured_LRA: {result["measured_LRA"]} (expected: 8.3)')
    print(f'  measured_TP: {result["measured_TP"]} (expected: -1.2)')
    print(f'  measured_thresh: {result["measured_thresh"]} (expected: -28.7)')
    print(f'  measured_offset: {result["measured_offset"]} (expected: 0.5)')
    
    assert result['measured_I'] == -18.5, f'Expected -18.5, got {result["measured_I"]}'
    assert result['measured_LRA'] == 8.3, f'Expected 8.3, got {result["measured_LRA"]}'
    assert result['measured_TP'] == -1.2, f'Expected -1.2, got {result["measured_TP"]}'
    assert result['measured_thresh'] == -28.7, f'Expected -28.7, got {result["measured_thresh"]}'
    assert result['measured_offset'] == 0.5, f'Expected 0.5, got {result["measured_offset"]}'


def test_parameter_parsing():
    """Test parameter parsing in __init__"""
    print()
    print('=== Testing Parameter Parsing ===')
    
    pp = FFmpegLoudnormPP(
        None,
        target_loudness='-16.0',
        target_lra='10.0',
        target_peak='-1.5',
        dual_mono=True
    )
    
    print(f'target_loudness: {pp.target_loudness} (type: {type(pp.target_loudness).__name__})')
    print(f'target_lra: {pp.target_lra} (type: {type(pp.target_lra).__name__})')
    print(f'target_peak: {pp.target_peak} (type: {type(pp.target_peak).__name__})')
    print(f'dual_mono: {pp.dual_mono}')
    
    assert pp.target_loudness == -16.0, f'Expected -16.0, got {pp.target_loudness}'
    assert pp.target_lra == 10.0, f'Expected 10.0, got {pp.target_lra}'
    assert pp.target_peak == -1.5, f'Expected -1.5, got {pp.target_peak}'
    assert pp.dual_mono is True, f'Expected True, got {pp.dual_mono}'


def test_default_values():
    """Test default values"""
    print()
    print('=== Testing Default Values ===')
    
    pp = FFmpegLoudnormPP(None)
    
    print(f'target_loudness: {pp.target_loudness} (expected: {FFmpegLoudnormPP.DEFAULT_TARGET_LOUDNESS})')
    print(f'target_lra: {pp.target_lra} (expected: {FFmpegLoudnormPP.DEFAULT_TARGET_LRA})')
    print(f'target_peak: {pp.target_peak} (expected: {FFmpegLoudnormPP.DEFAULT_TARGET_PEAK})')
    print(f'dual_mono: {pp.dual_mono} (expected: {FFmpegLoudnormPP.DEFAULT_DUAL_MONO})')
    print(f'linear_mode: {pp.linear_mode} (expected: True)')
    
    assert pp.target_loudness == FFmpegLoudnormPP.DEFAULT_TARGET_LOUDNESS
    assert pp.target_lra == FFmpegLoudnormPP.DEFAULT_TARGET_LRA
    assert pp.target_peak == FFmpegLoudnormPP.DEFAULT_TARGET_PEAK
    assert pp.dual_mono == FFmpegLoudnormPP.DEFAULT_DUAL_MONO
    assert pp.linear_mode is True


def test_methods_exist():
    """Test that all expected methods exist"""
    print()
    print('=== Testing Methods ===')
    
    pp = FFmpegLoudnormPP(None)
    methods = ['_get_audio_stream', '_measure_loudness', '_parse_loudnorm_output', 
               '_apply_normalization', 'run']
    
    for method in methods:
        exists = hasattr(pp, method) and callable(getattr(pp, method))
        print(f'Method {method}: exists={exists}')
        assert exists, f'Method {method} does not exist'


if __name__ == '__main__':
    test_import()
    test_class_attributes()
    test_parse_loudnorm_output()
    test_parameter_parsing()
    test_default_values()
    test_methods_exist()
    
    print()
    print('=' * 50)
    print('All tests passed!')
    print('=' * 50)
