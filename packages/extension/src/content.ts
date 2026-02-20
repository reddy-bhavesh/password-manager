(() => {
  if (window.location.protocol.startsWith("http")) {
    console.log("VaultGuard content script loaded", window.location.hostname);
  }
})();
