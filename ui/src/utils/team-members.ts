type TeamMemberLabelSource = {
  callsign?: string | null;
  display_name?: string | null;
  rns_identity?: string | null;
  uid?: string | null;
};

const firstNonEmptyText = (...values: Array<string | null | undefined>): string | null => {
  for (const value of values) {
    const text = String(value ?? "").trim();
    if (text) {
      return text;
    }
  }
  return null;
};

export const resolveTeamMemberPrimaryLabel = (
  member: TeamMemberLabelSource,
  options?: {
    identity?: string | null;
    uid?: string | null;
    fallback?: string;
  }
): string =>
  firstNonEmptyText(
    member.callsign,
    member.display_name,
    options?.identity ?? member.rns_identity,
    options?.uid ?? member.uid,
    options?.fallback ?? "Unknown member"
  ) ?? (options?.fallback ?? "Unknown member");
