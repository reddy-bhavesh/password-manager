import type { FieldError, FieldErrors, Resolver } from "react-hook-form";
import type { z } from "zod";

function toFieldError(message: string): FieldError {
  return {
    type: "validation",
    message
  };
}

export function zodResolver<TValues extends Record<string, unknown>>(
  schema: z.ZodType<TValues>
): Resolver<TValues> {
  return async (values) => {
    const parsed = schema.safeParse(values);

    if (parsed.success) {
      return {
        values: parsed.data,
        errors: {}
      };
    }

    const formErrors: FieldErrors<TValues> = {};
    const formErrorsMap = formErrors as Record<string, FieldError | undefined>;

    for (const issue of parsed.error.issues) {
      const key = issue.path[0];
      if (typeof key !== "string") {
        continue;
      }

      if (!formErrorsMap[key]) {
        formErrorsMap[key] = toFieldError(issue.message);
      }
    }

    return {
      values: {} as TValues,
      errors: formErrors
    };
  };
}
