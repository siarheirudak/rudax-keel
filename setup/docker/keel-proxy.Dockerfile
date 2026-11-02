FROM python:3.12-alpine
# Forward proxy and the local mock API. No extra listeners are installed.
WORKDIR /keel
CMD ["python3", "/keel/egress_proxy.py"]
