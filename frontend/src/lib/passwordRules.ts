/** The account password policy, the same as the backend (Requirement 1.5). */
export interface PasswordRule {
  key: string;
  label: string;
  test: (pw: string) => boolean;
}

export function buildPasswordRules(t: (key: string) => string): PasswordRule[] {
  return [
    { key: "minLength", label: t("passwordRules.minLength"), test: (pw) => pw.length >= 12 },
    { key: "uppercase", label: t("passwordRules.uppercase"), test: (pw) => /[A-Z]/.test(pw) },
    { key: "lowercase", label: t("passwordRules.lowercase"), test: (pw) => /[a-z]/.test(pw) },
    { key: "digit", label: t("passwordRules.digit"), test: (pw) => /[0-9]/.test(pw) },
    { key: "symbol", label: t("passwordRules.symbol"), test: (pw) => /[@$!]/.test(pw) },
  ];
}
