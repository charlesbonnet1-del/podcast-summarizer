import { redirect } from "next/navigation";

// Redirect to main settings page
export default function DashboardSettingsPage() {
  redirect("/settings");
}
