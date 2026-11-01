import * as React from "react"
import { cn } from "@/lib/utils"
import { CheckIcon } from "lucide-react"
import { Checkbox as CheckboxPrimitive } from "radix-ui"

function Checkbox({
  className,
  ...props
}: React.ComponentProps<typeof CheckboxPrimitive.Root>) {
  return (
    <CheckboxPrimitive.Root
      data-slot="checkbox"
      className={cn(
        "peer size-4 shrink-0 rounded-[4px] border border-line2 shadow-xs transition-shadow outline-none focus-visible:border-accent focus-visible:ring-[3px] focus-visible:ring-accent/30 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-bad aria-invalid:ring-bad/20 data-[state=checked]:border-accent data-[state=checked]:bg-accent data-[state=checked]:text-on-accent",
        className
      )}
      {...props}
    >
      <CheckboxPrimitive.Indicator
        data-slot="checkbox-indicator"
        className="grid place-content-center text-current transition-none"
      >
        <CheckIcon className="size-3.5" />
      </CheckboxPrimitive.Indicator>
    </CheckboxPrimitive.Root>
  )
}

export { Checkbox }
