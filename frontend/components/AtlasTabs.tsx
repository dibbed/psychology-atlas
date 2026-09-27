"use client";

import type { KeyboardEvent } from "react";

type Tab<T extends string> = readonly [T, string];

export default function AtlasTabs<T extends string>({ tabs, active, onChange, label, idPrefix, className = "" }: {
  tabs: readonly Tab<T>[];
  active: T;
  onChange: (next: T) => void;
  label: string;
  idPrefix: string;
  className?: string;
}) {
  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const current = tabs.findIndex(([id]) => id === active);
    let next = current;
    if (event.key === "ArrowLeft") next = (current + 1) % tabs.length;
    else if (event.key === "ArrowRight") next = (current - 1 + tabs.length) % tabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = tabs.length - 1;
    else return;
    event.preventDefault();
    onChange(tabs[next][0]);
    event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
  }
  return <div className={`tabs ${className}`} role="tablist" aria-label={label} onKeyDown={onKeyDown}>
    {tabs.map(([id, text]) => <button className={`tab ${active === id ? "active" : ""}`} key={id} id={`${idPrefix}-${id}`} type="button" onClick={() => onChange(id)} role="tab" tabIndex={active === id ? 0 : -1} aria-controls={`${idPrefix}-panel`} aria-selected={active === id}>{text}</button>)}
  </div>;
}
