#!/usr/bin/env python3
"""Download files from Google Drive"""

import os
import gdown

# Create data directory
data_dir = "/home/user/zk-2048/btc_trading_strategy/data"
os.makedirs(data_dir, exist_ok=True)

# Google Drive file IDs and expected filenames
files = [
    ("1P2wdzvOr_760ZYT5yG13IrWz0KZdn8tH", "file1.csv"),
    ("1kvasYLVsm5nhrsgrz0bGW1fM08z6ZBde", "file2.csv"),
    ("1XHFwQJEkxQ1xSDKHz0ktUTGEPR65caIQ", "file3.csv"),
    ("1YcfVujp6XuQWjBxl0a9e2Lda07rFTxea", "file4.csv"),
    ("1vbxdrr4q2vO2nuHVu8ElxHWuOAdWLdJT", "file5.csv"),
    ("1jTVLB0ln1KERqOCtmPcGYUohEH0hzT_F", "file6.csv"),
    ("12U4OesZTQs21R5TNlhzKmp7Oyu87o0u0", "file7.csv"),
    ("1aVaZUqCRka5MdxYd33ECOItXVNqoHpkl", "file8.csv"),
    ("1lrbteA9udtg06IcfBu-c-hEY3mWJt0OU", "file9.csv"),
]

for file_id, default_name in files:
    url = f"https://drive.google.com/uc?id={file_id}"
    output = os.path.join(data_dir, default_name)
    print(f"Downloading {file_id}...")
    try:
        downloaded = gdown.download(url, output, quiet=False, fuzzy=True)
        if downloaded:
            print(f"  Saved to: {downloaded}")
    except Exception as e:
        print(f"  Error: {e}")
    print()

# List downloaded files
print("\nDownloaded files:")
for f in os.listdir(data_dir):
    filepath = os.path.join(data_dir, f)
    size = os.path.getsize(filepath) / (1024*1024)
    print(f"  {f}: {size:.2f} MB")
