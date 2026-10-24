import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "radix-ui";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  [
    "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-control border-0 font-heading font-bold text-heading",
    "cursor-pointer transition-[filter,transform] duration-200 ease-in-out",
    "hover:scale-[1.04] hover:brightness-[0.85]",
    "motion-reduce:transition-none motion-reduce:hover:scale-100",
    "disabled:pointer-events-none disabled:opacity-60",
  ],
  {
    variants: {
      variant: {
        primary: "bg-purple p-4 text-base",
        secondary: "h-[38px] bg-teal px-4 text-[0.9rem]",
        ghost: "h-[38px] border border-solid border-body bg-transparent px-4 text-[0.85rem] text-body",
        pill: "rounded-full bg-purple px-3 py-1.5 text-xs",
      },
      fullWidth: { true: "w-full", false: "" },
    },
    defaultVariants: { variant: "primary", fullWidth: false },
  },
);

interface ButtonProps
  extends React.ComponentProps<"button">,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

function Button({ className, variant, fullWidth, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot.Root : "button";
  return <Comp className={cn(buttonVariants({ variant, fullWidth }), className)} {...props} />;
}

export { Button, buttonVariants };
