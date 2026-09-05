/**
 * useRazorpayCheckout — Phase 6.
 *
 * Loads Razorpay Checkout.js script dynamically (only when needed),
 * opens the modal for an approved transaction, and calls the server-side
 * verify endpoint after payment.success fires.
 *
 * Security:
 *  - KEY_ID is fetched from GET /api/payments/config (public, server-validated).
 *  - KEY_SECRET is never present in frontend code or responses.
 *  - Payment is only considered verified once POST /api/payments/verify
 *    returns { verified: true } from the server — frontend success state alone
 *    is never sufficient.
 */
import { useCallback, useRef } from "react";
import { api, PaymentVerifyResponse } from "./api";

declare global {
  interface Window {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    Razorpay: any;
  }
}

/** Options passed to openCheckout */
export interface CheckoutOptions {
  /** Razorpay order_id returned by the checkout MCP tool */
  razorpay_order_id: string;
  /** Cart total in ₹ (displayed in the modal) */
  amount: number;
  /** Internal transaction ID for correlation */
  transaction_id: string;
  /** Bearer token for the verify call */
  token: string;
  /** Called with the verification result after server-side verify completes */
  onVerified: (result: PaymentVerifyResponse) => void;
  /** Called if Checkout.js modal is dismissed or Razorpay errors */
  onDismissed: () => void;
}

/** Load the Razorpay Checkout.js script exactly once per page load */
function loadCheckoutScript(): Promise<void> {
  return new Promise((resolve, reject) => {
    if (window.Razorpay) {
      resolve();
      return;
    }
    const script = document.createElement("script");
    script.src = "https://checkout.razorpay.com/v1/checkout.js";
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Failed to load Razorpay Checkout.js"));
    document.head.appendChild(script);
  });
}

export function useRazorpayCheckout() {
  const rzpRef = useRef<unknown>(null);

  const openCheckout = useCallback(async (opts: CheckoutOptions) => {
    // 1. Load script
    await loadCheckoutScript();

    // 2. Fetch public KEY_ID (never the secret)
    const config = await api.getPaymentConfig(opts.token);

    // 3. Open Checkout.js modal
    const rzp = new window.Razorpay({
      key: config.key_id,
      amount: Math.round(opts.amount * 100),   // paise
      currency: config.currency,
      order_id: opts.razorpay_order_id,
      name: "AI Commerce Gateway",
      description: "AI-selected purchase",
      // No prefill — demo buyer uses test card directly

      handler: async function (response: {
        razorpay_payment_id: string;
        razorpay_order_id: string;
        razorpay_signature: string;
      }) {
        // 4. Verify server-side — payment is NOT considered verified until this returns
        const result = await api.verifyPayment(
          {
            razorpay_order_id: response.razorpay_order_id,
            razorpay_payment_id: response.razorpay_payment_id,
            razorpay_signature: response.razorpay_signature,
          },
          opts.token
        );
        opts.onVerified(result);
      },

      modal: {
        ondismiss: opts.onDismissed,
      },

      theme: {
        color: "#191A23",   // --ink from design system
      },
    });

    rzpRef.current = rzp;
    rzp.open();
  }, []);

  return { openCheckout };
}
