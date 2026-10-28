export const MOCK_MODE =
  new URLSearchParams(window.location.search).get("mock") === "1" ||
  import.meta.env.VITE_MOCK === "1";
