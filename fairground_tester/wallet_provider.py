import json
from typing import Any

from eth_account import Account
from eth_account.messages import encode_defunct
from loguru import logger

try:
    from eth_account.messages import encode_typed_data
except ImportError:  # pragma: no cover
    encode_typed_data = None


class BrowserWallet:
    def __init__(self, private_key: str, chain_id: str = "0x1"):
        self.account = Account.from_key(private_key)
        self.address = self.account.address
        self.chain_id = chain_id

    async def handle_request(self, payload: dict[str, Any]) -> Any:
        method = payload.get("method")
        params = payload.get("params") or []
        logger.info(f"Wallet RPC: {method}")

        if method in {"eth_requestAccounts", "eth_accounts"}:
            return [self.address]
        if method == "eth_chainId":
            return self.chain_id
        if method == "net_version":
            return str(int(self.chain_id, 16))
        if method in {"wallet_switchEthereumChain", "wallet_addEthereumChain"}:
            if params and isinstance(params[0], dict) and params[0].get("chainId"):
                self.chain_id = params[0]["chainId"]
            return None
        if method == "personal_sign":
            return self._sign_personal(params)
        if method == "eth_sign":
            message = params[1] if len(params) > 1 else params[0]
            return self._sign_personal(message)
        if method in {"eth_signTypedData", "eth_signTypedData_v3", "eth_signTypedData_v4"}:
            typed = params[1] if len(params) > 1 else params[0]
            return self._sign_typed_data(typed)
        if method == "wallet_watchAsset":
            return False
        if method == "wallet_getCapabilities":
            return {}
        if method == "wallet_getPermissions":
            return [{"parentCapability": "eth_accounts"}]
        if method == "wallet_requestPermissions":
            return [{"parentCapability": "eth_accounts"}]
        if method == "web3_clientVersion":
            return "FairgroundTestWallet/1.0"
        if method == "eth_sendTransaction":
            raise ValueError("eth_sendTransaction is intentionally not supported by this tester")

        raise ValueError(f"Unsupported wallet request method: {method}")

    def _sign_personal(self, message: str) -> str:
        if isinstance(message, list):
            lowered = self.address.lower()
            if len(message) > 1 and str(message[0]).lower() == lowered:
                message = message[1]
            else:
                message = message[0]
        if isinstance(message, str) and message.startswith("0x"):
            signable = encode_defunct(hexstr=message)
        else:
            signable = encode_defunct(text=str(message))
        signed = Account.sign_message(signable, self.account.key)
        return "0x" + signed.signature.hex().removeprefix("0x")

    def _sign_typed_data(self, typed: str | dict[str, Any]) -> str:
        if encode_typed_data is None:
            raise ValueError("eth-account version does not support typed data signing")
        full_message = json.loads(typed) if isinstance(typed, str) else typed
        signable = encode_typed_data(full_message=full_message)
        signed = Account.sign_message(signable, self.account.key)
        return "0x" + signed.signature.hex().removeprefix("0x")


INJECTED_PROVIDER_SCRIPT = r"""
(() => {
  if (window.__fairgroundWalletInjected) return;
  window.__fairgroundWalletInjected = true;

  const address = "__ADDRESS__";
  const chainId = "__CHAIN_ID__";
  const listeners = new Map();

  function emit(event, value) {
    const items = listeners.get(event) || [];
    for (const fn of items) {
      try { fn(value); } catch (err) {}
    }
  }

  const provider = {
    isMetaMask: true,
    isConnected: () => true,
    selectedAddress: address,
    chainId,
    networkVersion: String(parseInt(chainId, 16)),
    request: async (args) => {
      const result = await window.__fairgroundWalletRequest(args || {});
      if (args && args.method === "eth_requestAccounts") {
        emit("connect", { chainId });
        emit("accountsChanged", [address]);
      }
      return result;
    },
    enable: async () => [address],
    on: (event, fn) => {
      const items = listeners.get(event) || [];
      items.push(fn);
      listeners.set(event, items);
      return provider;
    },
    removeListener: (event, fn) => {
      const items = listeners.get(event) || [];
      listeners.set(event, items.filter((item) => item !== fn));
      return provider;
    },
  };

  Object.defineProperty(window, "ethereum", {
    value: provider,
    writable: false,
    configurable: true,
  });

  const info = {
    uuid: "350670db-19fa-4704-a166-e52e178b59d2",
    name: "Fairground Test Wallet",
    icon: "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg'/>",
    rdns: "fi.fairground.testwallet",
  };

  function announce() {
    window.dispatchEvent(new CustomEvent("eip6963:announceProvider", {
      detail: Object.freeze({ info, provider }),
    }));
  }
  window.addEventListener("eip6963:requestProvider", announce);
  announce();
})();
"""


def provider_script(address: str, chain_id: str) -> str:
    return INJECTED_PROVIDER_SCRIPT.replace("__ADDRESS__", address).replace("__CHAIN_ID__", chain_id)
