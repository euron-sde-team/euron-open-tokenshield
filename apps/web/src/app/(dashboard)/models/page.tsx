import type { Metadata } from "next";
import { Suspense } from "react";

import { ModelsScreen } from "@/features/models/components/models-screen";

export const metadata: Metadata = { title: "Models" };

export default function Page() {
  return (
    <Suspense>
      <ModelsScreen />
    </Suspense>
  );
}
