# Deployment on single machines with multiple GPUs

The docker-compose files in this repo are intended for single instance GPU deployment. 
E.g. A single EC2 or a GCP instance. For several one-off workloads this is good enough.

- install_cuda_drivers.sh install CUDA along with drivers on GCP Ubuntu Xenial VM ( Not need for AWS since the DL AMI contains pre-installed drivers.)

- docker-compose-gpu.yml : Docker compose file for single GPU with at last 12 Gb VRAM.

- docker-compose-<n>-gpus.yml : Docker compose file for multiple GPUs.

- fix_docker_compose.py : make nvidia-docker default runtime.

- install_docker.sh :  install compatible docker version, make sure you log out and log in.

- install_nvidia_docker.sh install nvidia docker and make it default runtime.

- /aws instructions for using P2 instance and AMI

- /gcp instructions for using Google Cloud Platform cloud VM

#### The docker-compose files use loop back interface (127.0.0.1:8000:80), we recommend forwarding the host OS port (8000)
over SSH tunnel when using cloud providers or VPS services such as Linode.