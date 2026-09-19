/**
 * Safe formatting helpers for currency, numbers, and dates.
 * 
 * Invariants:
 * - Preserves distinction between missing data (null / undefined / NaN) -> "—"
 *   and real zero (0) -> "₹0" / "0".
 * - Never throws TypeError if an API field is missing or undefined.
 */

export interface NumberFormatOptions extends Intl.NumberFormatOptions {}

export interface CurrencyFormatOptions {
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
}

/**
 * Format numeric quantities (e.g. units sold, counts).
 * Returns "—" for null, undefined, or non-finite values.
 */
export const formatNumber = (
  value: number | null | undefined,
  options?: NumberFormatOptions
): string => {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value.toLocaleString("en-IN", options);
  }
  return "—";
};

/**
 * Format currency amounts in INR (₹).
 * Returns "—" for null, undefined, or non-finite values.
 * Real zero (0) returns "₹0" (or "₹0.00" if fraction digits specified).
 */
export const formatCurrency = (
  value: number | null | undefined,
  options?: CurrencyFormatOptions
): string => {
  if (typeof value === "number" && Number.isFinite(value)) {
    const formatted = value.toLocaleString("en-IN", {
      minimumFractionDigits: options?.minimumFractionDigits,
      maximumFractionDigits: options?.maximumFractionDigits,
    });
    return `₹${formatted}`;
  }
  return "—";
};

/**
 * Format ISO date strings or Date objects safely.
 * Returns "—" for null, undefined, or invalid dates.
 */
export const formatDate = (
  value: string | number | Date | null | undefined,
  options?: Intl.DateTimeFormatOptions
): string => {
  if (!value) return "—";
  try {
    const d = new Date(value);
    if (isNaN(d.getTime())) return "—";
    return d.toLocaleString("en-IN", options);
  } catch {
    return "—";
  }
};
