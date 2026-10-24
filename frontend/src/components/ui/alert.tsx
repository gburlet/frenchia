import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const alertVariants = cva("rounded-control border-l-4 bg-chrome px-4 py-3 text-sm", {
  variants: {
    variant: {
      error: "border-failure text-error-text",
      warning: "border-blocked text-warning-text",
      success: "border-success text-kept",
    },
  },
  defaultVariants: { variant: "error" },
});

function Alert({
  className,
  variant,
  ...props
}: React.ComponentProps<"div"> & VariantProps<typeof alertVariants>) {
  return <div role="alert" className={cn(alertVariants({ variant }), className)} {...props} />;
}

function AlertTitle({ className, ...props }: React.ComponentProps<"p">) {
  return <p className={cn("font-heading font-bold", className)} {...props} />;
}

function AlertDescription({ className, ...props }: React.ComponentProps<"p">) {
  return <p className={cn(className)} {...props} />;
}

export { Alert, AlertTitle, AlertDescription };
