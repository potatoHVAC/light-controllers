FROM python:3.12-slim
# The project is mounted at /firmware at run time (see server/run.sh); the
# server runs as a module from there. No application code is baked into the
# image, so edits take effect on restart without a rebuild.
WORKDIR /firmware
CMD ["python3", "-m", "server.app"]
