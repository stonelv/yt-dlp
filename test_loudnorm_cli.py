#!/usr/bin/env python3
"""Test CLI integration for FFmpegLoudnormPP"""

import sys
sys.path.insert(0, '/Users/lvzhe/github/GSB/yt-dlp')

from unittest.mock import MagicMock


def test_get_postprocessors():
    """Test that get_postprocessors correctly generates FFmpegLoudnorm config"""
    print('=== Testing get_postprocessors Integration ===')
    
    from yt_dlp import _real_main
    from yt_dlp.options import parseOpts
    from yt_dlp import get_postprocessors
    
    # 测试带默认参数的 --normalize-loudness
    test_args = ['--normalize-loudness', 'https://example.com/test']
    parser, opts, args = parseOpts(test_args)
    
    print(f'  normalizeloudness: {opts.normalizeloudness}')
    print(f'  targetloudness: {opts.targetloudness}')
    print(f'  targetlra: {opts.targetlra}')
    print(f'  targetpeak: {opts.targetpeak}')
    print(f'  dualmono: {opts.dualmono}')
    
    # 检查 get_postprocessors 是否生成正确的配置
    pps = list(get_postprocessors(opts))
    loudnorm_pp = None
    for pp in pps:
        if pp.get('key') == 'FFmpegLoudnorm':
            loudnorm_pp = pp
            break
    
    assert loudnorm_pp is not None, 'FFmpegLoudnorm PP not found in postprocessors'
    print(f'  Generated PP config: {loudnorm_pp}')
    
    assert loudnorm_pp['target_loudness'] == '-24.0'
    assert loudnorm_pp['target_lra'] == '7.0'
    assert loudnorm_pp['target_peak'] == '-2.0'
    assert loudnorm_pp['dual_mono'] == False
    
    print()
    print('=== Testing with Custom Parameters ===')
    
    # 测试带自定义参数的 --loudnorm
    test_args2 = [
        '--loudnorm',
        '--target-loudness', '-16.0',
        '--target-lra', '10.0',
        '--target-peak', '-1.5',
        '--dual-mono',
        'https://example.com/test'
    ]
    parser2, opts2, args2 = parseOpts(test_args2)
    
    print(f'  normalizeloudness: {opts2.normalizeloudness}')
    print(f'  targetloudness: {opts2.targetloudness}')
    print(f'  targetlra: {opts2.targetlra}')
    print(f'  targetpeak: {opts2.targetpeak}')
    print(f'  dualmono: {opts2.dualmono}')
    
    pps2 = list(get_postprocessors(opts2))
    loudnorm_pp2 = None
    for pp in pps2:
        if pp.get('key') == 'FFmpegLoudnorm':
            loudnorm_pp2 = pp
            break
    
    assert loudnorm_pp2 is not None, 'FFmpegLoudnorm PP not found in postprocessors'
    print(f'  Generated PP config: {loudnorm_pp2}')
    
    assert loudnorm_pp2['target_loudness'] == '-16.0'
    assert loudnorm_pp2['target_lra'] == '10.0'
    assert loudnorm_pp2['target_peak'] == '-1.5'
    assert loudnorm_pp2['dual_mono'] == True
    
    print()
    print('=== Testing Without --normalize-loudness ===')
    
    # 测试不带 --normalize-loudness 的情况
    test_args3 = ['https://example.com/test']
    parser3, opts3, args3 = parseOpts(test_args3)
    
    print(f'  normalizeloudness: {opts3.normalizeloudness}')
    
    pps3 = list(get_postprocessors(opts3))
    has_loudnorm = any(pp.get('key') == 'FFmpegLoudnorm' for pp in pps3)
    
    assert not has_loudnorm, 'FFmpegLoudnorm should not be in postprocessors when --normalize-loudness is not used'
    print(f'  FFmpegLoudnorm in postprocessors: {has_loudnorm} (expected: False)')


def test_pp_key():
    """Test that pp_key is correctly registered"""
    print()
    print('=== Testing PP Key Registration ===')
    
    from yt_dlp.postprocessor import get_postprocessor, FFmpegLoudnormPP
    
    # 测试 get_postprocessor 是否能找到 FFmpegLoudnorm
    pp_class = get_postprocessor('FFmpegLoudnorm')
    print(f'  get_postprocessor("FFmpegLoudnorm"): {pp_class}')
    assert pp_class == FFmpegLoudnormPP
    
    # 测试 pp_key 是否正确
    print(f'  FFmpegLoudnormPP.pp_key(): {FFmpegLoudnormPP.pp_key()}')
    assert FFmpegLoudnormPP.pp_key() == 'Loudnorm'


if __name__ == '__main__':
    test_get_postprocessors()
    test_pp_key()
    
    print()
    print('=' * 50)
    print('All CLI integration tests passed!')
    print('=' * 50)
