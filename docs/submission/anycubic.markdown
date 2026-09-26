---
title: Anycubic
description: Instructions on how to monitor an Anycubic 3D printer in LAN Mode from Home Assistant.
ha_category:
  - 3D Printing
  - Sensor
ha_release: TBD
ha_iot_class: Local Push
ha_config_flow: true
ha_codeowners:
  - '@Nino6689'
ha_domain: anycubic
ha_integration_type: device
ha_dhcp: true
ha_platforms:
  - diagnostics
  - sensor
ha_quality_scale: bronze
---

<!-- DRAFT for Nino to review and rewrite in his own words before opening a PR against home-assistant.io. -->

The **Anycubic** {% term integration %} lets you monitor an [Anycubic](https://www.anycubic.com) 3D printer directly on your local network, without an Anycubic account and without the cloud. It talks to the printer's own LAN Mode service and shows the printer's status, temperatures and the progress of the current print.

Use case: get a notification when a print is done or when the printer reports an error, or show the remaining print time on a dashboard.

A separate community integration exists for features that need the Anycubic cloud (such as file management and cloud printing). This integration only covers local monitoring.

## Supported devices

The following printers are known to work:

- Anycubic Kobra S1 (tested with firmware 2.7.2.7)
- Anycubic Kobra X (firmware 2.0.2.2; based on logs, not tested by the maintainer)

Other Anycubic FDM printers that offer **LAN Mode** with the same handshake are expected to work and are shown as "Anycubic printer (model &lt;id&gt;)".

## Unsupported devices

- Kobra 2 and older models. They answer on the local network but do not offer LAN Mode; setup reports the printer as unsupported.

## Prerequisites

1. On the printer's screen, go to **Settings** > **Network** and connect the printer to your network.
2. In the same menu, switch on **LAN Mode**.
3. Note the printer's IP address, shown under **Settings** > **Network**. We recommend giving the printer a fixed address (a DHCP reservation) in your router.

While LAN Mode is on, the printer is not connected to the Anycubic cloud, so the Anycubic app and cloud printing do not work at the same time.

{% include integrations/config_flow.md %}

{% configuration_basic %}
Host:
    description: "The IP address or hostname of the printer, for example `192.168.1.50`. You can find it on the printer's screen under **Settings** > **Network**."
{% endconfiguration_basic %}

Home Assistant may discover the printer automatically through DHCP (Anycubic network hardware, or hostnames starting with `anycubic` or `kobra`). If a known printer is discovered at a new address, the entry is updated. You can also change it with **Reconfigure** on the integration entry.

## Supported functionality

The integration creates one device per printer with the following sensors.

- **Status**: overall printer state: Idle, Printing, Paused or Busy.
- **Nozzle temperature** and **Nozzle target temperature**
- **Bed temperature** and **Bed target temperature**
- **Chamber temperature**: only created on printers that report a chamber reading.
- **Fan speed** and **Auxiliary fan speed** (percent). Disabled by default.
- **Print progress** (percent)
- **Current layer** and **Total layers**
- **Print time** and **Remaining time** (minutes)
- **Print end time**: the time the current print is expected to finish.
- **Job name**: the file name of the current print, without folders or extension.
- **Job status**: Idle, Printing, Complete, Cancelled, Downloading, Checking, Preheating, Slicing or Levelling.
- **Speed mode**: Silent, Standard or Sport.
- **Last error code** (diagnostic): the most recent error code the printer reported, or `none`.

The print sensors are unknown when no print is running; **Job status** then reads Idle.

## Examples

### Notify when a print is complete

{% details "YAML example" %}

```yaml
alias: "Notify when the 3D print is complete"
triggers:
  - trigger: state
    entity_id: sensor.anycubic_kobra_s1_job_status
    to: complete
actions:
  - action: notify.notify
    data:
      message: "The print {{ states('sensor.anycubic_kobra_s1_job_name') }} is complete."
```

{% enddetails %}

## Data updates

The printer pushes its state to Home Assistant as it changes ({% term "Local Push" %}). Because the printer only reports some values when asked, the integration also asks the printer for all its values every 15 seconds.

## Known limitations

- The first version only provides sensors. Pausing, resuming and stopping prints, the printer light, the camera and ACE filament hub details are not available yet.
- LAN Mode and the Anycubic cloud cannot be used at the same time.
- Values the printer reports in a way the integration does not recognise (for example an unknown speed mode) are shown as unknown. The raw value is included in the diagnostics.

## Troubleshooting

{% details "The printer is not in LAN Mode" %}

### Symptom: "The printer answered, but LAN Mode is switched off"

#### Description

The printer is reachable, but LAN Mode is off, so it does not accept local connections.

#### Resolution

On the printer, go to **Settings** > **Network** and switch on **LAN Mode**, then try again.

{% enddetails %}

{% details "Failed to connect" %}

### Symptom: "Failed to connect"

#### Description

The printer did not answer at the address you entered.

#### Resolution

1. Make sure the printer is switched on and not asleep.
2. Check the IP address on the printer's screen under **Settings** > **Network**.
3. Make sure Home Assistant and the printer are on the same network and that port 18910 and 9883 are not blocked between them.

{% enddetails %}

{% details "The sensors become unavailable" %}

### Symptom: all sensors show unavailable

#### Description

The connection to the printer was lost, for example because the printer was switched off or restarted. The integration logs a single warning when this happens and reconnects on its own when the printer is back; it logs a message when the connection is restored.

#### Resolution

Switch the printer on. If its IP address changed and it is not rediscovered, use **Reconfigure** on the integration entry to enter the new address.

{% enddetails %}

## Removing the integration

This integration follows standard integration removal. No extra steps are required.

{% include integrations/remove_device_service.md %}

If you no longer want local access, you can switch off **LAN Mode** on the printer.
