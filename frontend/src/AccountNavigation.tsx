import { useEffect, useState } from "react";
import { LogIn, UserRound } from "lucide-react";
import { accountSession, type AccountSession } from "./cloudAccount";

export default function AccountNavigation({ open }: { open: (mode: "login" | "signup") => void }) {
  const [account, setAccount] = useState<AccountSession>();
  useEffect(() => { void accountSession().then(setAccount).catch(() => {}); }, []);
  return (
    <nav className="account-navigation" aria-label="Account">
      <button className="primary account-entry" onClick={() => open("login")}>
        {account?.user ? <UserRound size={16} /> : <LogIn size={16} />}
        {account?.user ? "My account" : "Log in"}
      </button>
    </nav>
  );
}
