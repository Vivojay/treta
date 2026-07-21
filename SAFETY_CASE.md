# Treta initial safety case

## Claim

The simulation-only MVP demonstrates supervisory safety behaviour without placing cloud communication in a physical flight-control loop (`TRETA-SAF-001`). It does not establish airworthiness or certification.

## Assumptions

- All vehicles, positions, missions, and failures are synthetic.
- The deterministic internal simulator is an operational model, not an aerodynamic model.
- Vehicle-local navigation, return, holding, landing, and emergency behaviour would be supplied and independently validated by a future trusted edge or flight controller.

## Hazards and mitigations

| Hazard | Current mitigation | Evidence target | Residual risk |
| --- | --- | --- | --- |
| Cloud outage causes unsafe flight | Reserve response resides in the simulated vehicle boundary | Local-safety tests | Physical implementation unverified |
| Unsafe drone assignment | Deterministic eligibility rules explain payload, health, connectivity, freshness, capability, and reserve rejection | Safety and scenario tests | Simplified energy/weather model |
| Transmitted command mistaken for execution | Command delivery, acknowledgement, execution, and observed state are distinct | State-machine and API tests | Real protocol acknowledgements absent |
| Battery falls below landing reserve | Local rule selects return or controlled landing and opens an incident | Boundary and replay tests | Simplified battery dynamics |

## Unresolved risks and limitations

Software-in-the-loop testing does not replace hardware-in-the-loop testing. Near-zero public-internet latency is not guaranteed. Real operations require regulator approval, insurance, operating procedures, trained personnel, airspace permission, hardware validation, redundancy, paid infrastructure with defined SLAs, and independent safety review.
