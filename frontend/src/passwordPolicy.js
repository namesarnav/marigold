/**
 * A client-side echo of `validate_password_strength` in backend/security.py.
 *
 * The backend is the authority — it re-checks every password and is the only
 * check that counts. This exists so the form can say what the rule is before
 * the user submits, instead of bouncing them off a 422 they could have been
 * warned about. Keep the two in step; if they drift, the server wins and the
 * only cost is a worse message.
 *
 * The backend also rejects passwords that merely contain the account's own
 * email or name, and a list of common passwords. Those are deliberately not
 * mirrored here: reproducing the list client-side would be a lot of bytes to
 * ship for a check that still has to run on the server.
 */

export const MIN_PASSWORD_LENGTH = 12;
export const MAX_PASSWORD_LENGTH = 128;

export const PASSWORD_HINT =
  "At least 12 characters, using three of: lowercase, uppercase, digits, symbols.";

/**
 * Returns a message describing the first unmet rule, or "" when it looks fine.
 */
export function checkPassword(password) {
  if (!password) return "Password is required.";

  if (password.length < MIN_PASSWORD_LENGTH) {
    return `Password must be at least ${MIN_PASSWORD_LENGTH} characters long.`;
  }
  if (password.length > MAX_PASSWORD_LENGTH) {
    return `Password must be at most ${MAX_PASSWORD_LENGTH} characters long.`;
  }

  const classes = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((re) =>
    re.test(password)
  ).length;

  if (classes < 3) {
    return "Password must include at least three of: lowercase, uppercase, digits, symbols.";
  }

  return "";
}
