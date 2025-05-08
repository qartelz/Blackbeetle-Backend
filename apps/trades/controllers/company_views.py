from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters import rest_framework as filters
from django.core.files.storage import default_storage
from ..models import Company
from ..serializers.company_serializers import CompanySerializer
from ..filters.company_filter import CompanyFilter
from ..pagination import CompanyPagination
from ..tasks import process_csv_file

class CompanyViewSet(viewsets.ModelViewSet):
    queryset = Company.objects.all()
    serializer_class = CompanySerializer
    filterset_class = CompanyFilter
    filter_backends = (filters.DjangoFilterBackend,)
    pagination_class = CompanyPagination


    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Check if we're looking for MCX exchange data
        if self.request.query_params.get('commodity'):
            print("------------------------------------------------------------")
            queryset = queryset.filter(exchange='MCX')
            
        return queryset.order_by('trading_symbol')

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)
        return Response(
            serializer.data, 
            status=status.HTTP_201_CREATED, 
            headers=headers
        )

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(
            instance, 
            data=request.data, 
            partial=partial
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response(serializer.data)

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        # Soft delete by setting is_active to False
        instance.is_active = False
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['POST'])
    def upload_csv(self, request):
        if 'file' not in request.FILES:
            return Response(
                {'error': 'No file provided'},
                status=status.HTTP_400_BAD_REQUEST
            )

        csv_file = request.FILES['file']
        if not csv_file.name.endswith('.csv'):
            return Response(
                {'error': 'File must be a CSV'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Save file temporarily
        file_path = default_storage.save(f'temp/company_uploads/{csv_file.name}', csv_file)
        
        # Process file asynchronously
        task = process_csv_file.delay(file_path)
        
        return Response({
            'message': 'File uploaded successfully. Processing started.',
            'task_id': task.id
        }, status=status.HTTP_202_ACCEPTED)
