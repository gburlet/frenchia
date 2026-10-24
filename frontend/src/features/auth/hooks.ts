import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchMe, login, logout } from "@/lib/api/endpoints";
import { queryKeys } from "@/lib/api/queryKeys";
import type { LoginRequest } from "@/lib/api/types";

/** `data` is the User, or null when logged out. */
export function useMe() {
  return useQuery({
    queryKey: queryKeys.me,
    queryFn: ({ signal }) => fetchMe(signal),
    staleTime: 60_000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: LoginRequest) => login(credentials),
    onSuccess: (user) => queryClient.setQueryData(queryKeys.me, user),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: logout,
    onSuccess: () => {
      queryClient.clear();
      queryClient.setQueryData(queryKeys.me, null);
    },
  });
}
