// Default runtime configuration, served next to the bundle.
//
// The container overwrites this file at start from the API_BASE_URL variable,
// so the API location can change without rebuilding the image. The bundle falls
// back to the build-time VITE_API_URL and then to the local compose API when
// this value is empty.
window.__API_BASE__ = '';
