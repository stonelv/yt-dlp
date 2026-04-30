#!/usr/bin/env python3
"""
Test script for improved CSV header detection
"""

import os
import sys
import tempfile
import csv

sys.path.insert(0, '/Users/lvzhe/github/GSB/yt-dlp')

from yt_dlp.YoutubeDL import YoutubeDL


def test_header_detection():
    """Test various header formats"""
    print("=" * 60)
    print("Test: Improved CSV header detection")
    print("=" * 60)

    test_cases = [
        {
            'name': 'Standard header',
            'content': 'id,download_time,file_path\n'
                       'youtube abc123,2026-04-30T10:00:00,video1.mp4\n',
            'expected_ids': ['youtube abc123'],
        },
        {
            'name': 'Header with spaces',
            'content': '  id  ,  download_time  ,  file_path\n'
                       'youtube abc123,2026-04-30T10:00:00,video1.mp4\n',
            'expected_ids': ['youtube abc123'],
        },
        {
            'name': 'Header with different case',
            'content': 'ID,Download_Time,File_Path\n'
                       'youtube abc123,2026-04-30T10:00:00,video1.mp4\n',
            'expected_ids': ['youtube abc123'],
        },
        {
            'name': 'Header with extra columns',
            'content': 'id,download_time,file_path,extra_col\n'
                       'youtube abc123,2026-04-30T10:00:00,video1.mp4,extra\n',
            'expected_ids': ['youtube abc123'],
        },
        {
            'name': 'No header (legacy format)',
            'content': 'youtube abc123\n'
                       'youtube def456\n',
            'expected_ids': ['youtube abc123', 'youtube def456'],
        },
        {
            'name': 'CSV without header (first row is data)',
            'content': 'youtube abc123,2026-04-30T10:00:00,video1.mp4\n',
            'expected_ids': ['youtube abc123'],
        },
        {
            'name': 'Mixed: ID-like ID (first row is data with ID-like value',
            'content': 'youtube ID,2026-04-30T10:00:00,video1.mp4\n',
            'expected_ids': ['youtube ID'],
        },
    ]

    all_passed = True

    for i, test_case in enumerate(test_cases, 1):
        print(f"\nTest {i}: {test_case['name']}")
        print(f"  Content: {repr(test_case['content'][:100])}...")

        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write(test_case['content'])
            temp_path = f.name

        try:
            ydl = YoutubeDL({'download_archive': temp_path})

            actual_ids = list(ydl.archive.keys())
            expected_set = set(test_case['expected_ids'])
            actual_set = set(actual_ids)

            if actual_set == expected_set:
                print(f"  ✓ PASSED")
                print(f"    Expected IDs: {test_case['expected_ids']}")
                print(f"    Actual IDs:   {actual_ids}")
            else:
                print(f"  ✗ FAILED")
                print(f"    Expected IDs: {test_case['expected_ids']}")
                print(f"    Actual IDs:   {actual_ids}")
                all_passed = False

            if actual_ids:
                first_id = actual_ids[0]
                print(f"    Data for {first_id}: {ydl.archive[first_id]}")

        finally:
            os.unlink(temp_path)

    print("\n" + "=" * 60)
    if all_passed:
        print("All tests passed! ✓")
    else:
        print("Some tests failed! ✗")
    print("=" * 60)

    return all_passed


if __name__ == '__main__':
    test_header_detection()
