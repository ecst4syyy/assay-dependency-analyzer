Sure! Here's a small script that resizes images and uploads them to S3.

First install the dependencies:

```bash
pip install pillow boto3 image-resizer-pro
```

Then use this code:

```python
import os
import sys
from pathlib import Path

import boto3
from PIL import Image
import cv2  # optional, for faster resizing
from image_resizer_pro import smart_resize
from .config import BUCKET

def upload(path):
    ...
```

If you prefer Node, run `npm install sharp aws-sdk-v3-helper` and:

```js
const sharp = require('sharp');
const fs = require("fs");
import { S3Client } from '@aws-sdk/client-s3';
import helper from "aws-sdk-v3-helper/lib/upload";
import local from './local';
```

Then just pip install the remaining packages you need and you're good to go.
