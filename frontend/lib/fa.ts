export function faNumber(value: number | string) {
  const number = typeof value === "string" ? Number(value) : value;
  if (Number.isNaN(number)) return String(value);
  return new Intl.NumberFormat("fa-IR").format(number);
}

export function faPercent(value: number | string) {
  return `${faNumber(value)}٪`;
}
