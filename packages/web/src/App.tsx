import { useForm } from "react-hook-form";
import * as Dialog from "@radix-ui/react-dialog";
import { z } from "zod";
import { create } from "zustand";

const demoSchema = z.object({
  email: z.string().email("Enter a valid email")
});

type DemoFormValues = z.infer<typeof demoSchema>;

type UiState = {
  dialogOpen: boolean;
  setDialogOpen: (open: boolean) => void;
};

const useUiStore = create<UiState>((set) => ({
  dialogOpen: false,
  setDialogOpen: (dialogOpen) => set({ dialogOpen })
}));

export function App() {
  const { register, handleSubmit, formState } = useForm<DemoFormValues>({
    defaultValues: {
      email: ""
    },
    mode: "onBlur"
  });

  const { dialogOpen, setDialogOpen } = useUiStore();

  const onSubmit = (values: DemoFormValues) => {
    const result = demoSchema.safeParse(values);
    if (result.success) {
      setDialogOpen(true);
    }
  };

  return (
    <main className="page">
      <section className="card">
        <h1>VaultGuard</h1>
        <p className="subtitle">React + Vite workspace is configured and running.</p>

        <form className="form" onSubmit={handleSubmit(onSubmit)} noValidate>
          <label htmlFor="email">Work Email</label>
          <input id="email" type="email" placeholder="name@company.com" {...register("email")} />
          {formState.errors.email ? (
            <p className="error">{formState.errors.email.message}</p>
          ) : (
            <p className="hint">Validated with React Hook Form + Zod.</p>
          )}
          <button type="submit">Open Dialog</button>
        </form>
      </section>

      <Dialog.Root open={dialogOpen} onOpenChange={setDialogOpen}>
        <Dialog.Portal>
          <Dialog.Overlay className="overlay" />
          <Dialog.Content className="dialog">
            <Dialog.Title>Component Libraries Wired</Dialog.Title>
            <Dialog.Description>
              Radix UI, Zustand, TanStack Query, TanStack Router, Framer Motion, React Hook Form, and Zod are
              available in this frontend skeleton.
            </Dialog.Description>
            <button type="button" onClick={() => setDialogOpen(false)}>
              Close
            </button>
          </Dialog.Content>
        </Dialog.Portal>
      </Dialog.Root>
    </main>
  );
}
