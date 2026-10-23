import type { Metadata } from "next";

import { TeamsScreen } from "@/features/teams/components/teams-screen";

export const metadata: Metadata = { title: "Teams" };

export default function Page() {
  return <TeamsScreen />;
}
