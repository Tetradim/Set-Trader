import React from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { useWebSocket } from "@/hooks/useWebSocket";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { PlusCircle } from "lucide-react";

const formSchema = z.object({
  symbol: z.string().min(2, "Symbol must be at least 2 chars").toUpperCase(),
  base_power: z.coerce.number().min(1, "Base power must be at least 1"),
});

export function AddTickerDialog() {
  const { sendMessage } = useWebSocket();
  const [open, setOpen] = React.useState(false);

  const form = useForm<z.infer<typeof formSchema>>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      symbol: "",
      base_power: 10,
    },
  });

  function onSubmit(values: z.infer<typeof formSchema>) {
    sendMessage("ADD_TICKER", values);
    form.reset();
    setOpen(false); 
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button className="gap-2">
          <PlusCircle size={16} /> Add Ticker
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-[425px]">
        <DialogHeader>
          <DialogTitle>Add New Trading Pair</DialogTitle>
          <DialogDescription>
            Enter the ticker symbol and base power to start the bot.
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="symbol"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Symbol (e.g. BTCUSDT)</FormLabel>
                  <FormControl>
                    <Input placeholder="BTCUSDT" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <FormField
              control={form.control}
              name="base_power"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Base Power (Leverage/Size)</FormLabel>
                  <FormControl>
                    <Input type="number" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />
            <Button type="submit" className="w-full">
              Add to Bracket Bot
            </Button>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}