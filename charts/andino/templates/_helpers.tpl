{{/*
Expand the name of the chart.
*/}}
{{- define "andino.name" -}}
{{- .Values.agent.name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Namespace: uses agent.namespace if set, otherwise andino-{agent.name}
*/}}
{{- define "andino.namespace" -}}
{{- if .Values.agent.namespace -}}
{{- .Values.agent.namespace }}
{{- else -}}
andino-{{ .Values.agent.name }}
{{- end -}}
{{- end }}

{{/*
Common labels
*/}}
{{- define "andino.labels" -}}
app.kubernetes.io/name: {{ include "andino.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "andino.selectorLabels" -}}
app.kubernetes.io/name: {{ include "andino.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
ServiceAccount name
*/}}
{{- define "andino.serviceAccountName" -}}
{{ include "andino.name" . }}
{{- end }}

{{/*
Config checksum annotation (triggers pod restart on config change)
*/}}
{{- define "andino.configChecksum" -}}
checksum/config: {{ include (print .Template.BasePath "/configmap.yaml") . | sha256sum }}
{{- end }}
