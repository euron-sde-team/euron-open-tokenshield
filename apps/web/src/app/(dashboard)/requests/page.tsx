import type { Metadata } from "next";
import { Suspense } from "react";

import { RequestsScreen } from "@/features/requests/components/requests-screen";

export const metadata: Metadata = { title: "Requests" };

export default function Page() {
  return (
    <Suspense>
      <RequestsScreen />
    </Suspense>
  );
}
