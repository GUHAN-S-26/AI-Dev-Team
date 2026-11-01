FROM mcr.microsoft.com/playwright/python@sha256:640d578aae63cfb632461d1b0aecb01414e4e020864ac3dd45a868dc0eff3078

# The Microsoft image supplies pinned browser binaries and OS dependencies;
# install the matching Python binding explicitly because it is not included in
# the base image.
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
    playwright==1.55.0 pytest==8.3.3

# The browser worker also starts the authenticated dashboard for acceptance
# tests. Install only the application's declared runtime libraries; the app
# source is mounted per test and no host environment or secrets are copied.
RUN python -m pip install --no-cache-dir --disable-pip-version-check \
    pydantic==2.13.5 openai==2.54.0 Pillow==11.3.0

USER 65532:65532
