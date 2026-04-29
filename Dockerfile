# The devcontainer should use the developer target and run as root with podman
# or docker with user namespaces.
FROM ghcr.io/diamondlightsource/ubuntu-devcontainer:noble AS developer

# Add any system dependencies for the developer/build environment here
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    graphviz tclsh tcl-dev imagemagick

WORKDIR /tmp

# Install apptainer to allow us to run apptainer images from matlab
RUN wget https://github.com/apptainer/apptainer/releases/download/v1.4.5/apptainer_1.4.5_amd64.deb \
    && apt install -y ./apptainer_1.4.5_amd64.deb

# Install environment-modules
RUN curl -LJO https://github.com/envmodules/modules/releases/download/v5.6.1/modules-5.6.1.tar.gz \
    && tar xfz modules-5.6.1.tar.gz \
    && cd modules-5.6.1 && ./configure && make && make install \
    && ln -s /usr/local/Modules/init/profile.sh /etc/profile.d/modules.sh \
    && ln -s /usr/local/Modules/init/profile.csh /etc/profile.d/modules.csh

ENV MODULEPATH=/dls_sw/deploy-tools/modulefiles

RUN apt-get dist-clean
# The build stage installs the context into the venv
FROM developer AS build

# Change the working directory to the `app` directory
# and copy in the project
WORKDIR /app
COPY . /app
RUN chmod o+wrX .

# Tell uv sync to install python in a known location so we can copy it out later
ENV UV_PYTHON_INSTALL_DIR=/python

# Sync the project without its dev dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-editable --no-dev --managed-python


# The runtime stage copies the built venv into a runtime container
FROM ubuntu:noble AS runtime

# Add apt-get system dependecies for runtime here if needed
RUN apt-get update -y && apt-get install -y --no-install-recommends \
    apptainer \
    && apt-get dist-clean

# Copy the python installation from the build stage
COPY --from=build /python /python

# Copy the environment, but not the source code
COPY --from=build /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH

# change this entrypoint if it is not the same as the repo
ENTRYPOINT ["dls-phoebus-converter"]
CMD ["--version"]
