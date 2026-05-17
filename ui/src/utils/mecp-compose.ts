export interface MecpComposeInput {
  severity: string;
  eventCode: string;
  details: string;
}

export function encodeMecpLogContent(input: MecpComposeInput): string {
  const severity = input.severity.trim();
  const eventCode = input.eventCode.trim().toUpperCase();
  const details = input.details.trim();
  return details ? `MECP/${severity}/${eventCode} ${details}` : `MECP/${severity}/${eventCode}`;
}
