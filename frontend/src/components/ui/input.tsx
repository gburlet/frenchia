import * as React from "react";
import { cn } from "@/lib/utils";

function Input({ className, type, ...props }: React.ComponentProps<"input">) {
  return (
    <input
      type={type}
      className={cn(
        "h-11 w-full rounded-control border border-line bg-chrome px-3 text-base text-heading placeholder:text-muted",
        "transition-colors duration-200 focus-visible:border-purple focus-visible:outline-purple",
        "disabled:cursor-not-allowed disabled:opacity-60 aria-invalid:border-failure",
        className,
      )}
      {...props}
    />
  );
}

export { Input };
