chrome.runtime.onInstalled.addListener(() => {
  console.log("VaultGuard extension installed");
});

chrome.runtime.onMessage.addListener((_message, _sender, sendResponse) => {
  sendResponse({ status: "ok" });
  return false;
});
