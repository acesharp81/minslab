import { Button as ButtonPrimitive } from "@base-ui/react/button"
import { cva, type VariantProps } from "class-variance-authority"
import { cn } from "cn"

/* 이 앱의 단추 두 가지(옛 .btn · .btn.sec): 주색 채움과 테두리만. 링크로 쓸 때는 <a className={buttonVariants({ variant })}> 로 쓴다(마진은 쓰는 곳에서 준다). */
const buttonVariants = cva(
  "inline-flex items-center gap-1.5 rounded-[10px] px-4 py-[9px] font-bold no-underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground hover:brightness-[1.06]",
        outline: "border-[1.5px] border-line2 bg-transparent text-foreground hover:brightness-[1.06]",
      },
    },
    defaultVariants: { variant: "default" },
  }
)

function Button({ className, variant = "default", ...props }: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return <ButtonPrimitive data-slot="button" className={cn(buttonVariants({ variant, className }))} {...props} />
}

export { Button, buttonVariants }
