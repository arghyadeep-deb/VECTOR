# VECTOR-INGESTED — personalized for VectorCode runtime
# Source: .claude/skills/check_fillable_fields.py

import sys
from pypdf import PdfReader




reader = PdfReader(sys.argv[1])
if (reader.get_fields()):
    print("This PDF has fillable form fields")
else:
    print("This PDF does not have fillable form fields; you will need to visually determine where to enter data")
