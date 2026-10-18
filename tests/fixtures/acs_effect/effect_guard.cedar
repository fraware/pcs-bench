// Real Cedar policy evaluated by the ACS runtime. The host owns enforcement.
// The constants are experiment fixtures, not an authenticated grant registry.
// A permit is explicit; any forbidding clause overrides the permit.
@id("effect_actor_mismatch")
forbid(principal, action, resource) when {
  context.tool_call.args.principal != "agent-1"
};
@id("effect_tenant_mismatch")
forbid(principal, action, resource) when {
  context.tool_call.args.tenant != "tenant-a"
};
@id("effect_resource_mismatch")
forbid(principal, action, resource) when {
  context.tool_call.args.resource != "account:a"
};
@id("effect_delta_excessive")
forbid(principal, action, resource) when {
  context.tool_call.args.delta > 10
};
@id("effect_delta_negative")
forbid(principal, action, resource) when {
  context.tool_call.args.delta < 0
};
@id("effect_revoked")
forbid(principal, action, resource) when {
  context.tool_call.args.policy_revoked == true
};
@id("effect_tool_mismatch")
forbid(principal, action, resource) when {
  context.tool_call.name != "commit_disposable_effect"
};
permit(principal, action, resource);
