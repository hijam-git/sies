// Development default. In production this file is overwritten by the
// container's entrypoint (see Dockerfile), which is how one built image is
// promoted between environments without a rebuild.
window.ENV = {
  API_URL: "/api"
};
